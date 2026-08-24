"""
Semantic clustering of filtered articles.

Uses DBSCAN on L2-normalized embeddings (equivalent to cosine distance) to:
  - Group articles into topic clusters
  - Identify "Top Cited" clusters (highest unique-source count)
  - Identify "Top Blindspots" (high relevance, low coverage)
"""
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize

from models import Article

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    cluster_id: int
    articles: List[Article] = field(default_factory=list)
    label: str = ""          # Set by analyzer
    summary: str = ""        # Set by analyzer
    impact: str = "Medium"   # High / Medium / Low — set by analyzer

    @property
    def unique_sources(self) -> int:
        return len({a.source for a in self.articles})

    @property
    def source_names(self) -> List[str]:
        return sorted({a.source for a in self.articles})

    @property
    def avg_relevance(self) -> float:
        if not self.articles:
            return 0.0
        return float(np.mean([a.relevance_score for a in self.articles]))

    @property
    def best_article(self) -> Article:
        """Article with highest relevance score — used as cluster representative."""
        return max(self.articles, key=lambda a: a.relevance_score)


def cluster_articles(
    articles: List[Article],
    config: dict,
) -> Tuple[List[Cluster], List[Article]]:
    """
    Cluster articles using DBSCAN on normalized embeddings.

    Returns:
        (clusters, blindspot_articles)
        - clusters: list of Cluster objects, sorted by unique_sources desc
        - blindspot_articles: singleton/noise articles with high relevance score
    """
    if not articles:
        return [], []

    # Only cluster articles that have embeddings
    embeddable = [a for a in articles if a.embedding is not None]
    if not embeddable:
        logger.warning("No articles with embeddings found — skipping clustering.")
        return [], []

    eps = config.get("cluster_eps", 0.35)
    min_samples = config.get("cluster_min_samples", 2)
    blindspot_min = config.get("blindspot_min_score", 0.65)
    top_cited_count = config.get("top_cited_count", 5)
    blindspot_count = config.get("blindspot_count", 5)

    # Stack and L2-normalize embeddings (cosine distance → euclidean on unit sphere)
    matrix = np.stack([a.embedding for a in embeddable])
    matrix = normalize(matrix, norm="l2")

    logger.info(f"Running DBSCAN (eps={eps}, min_samples={min_samples}) on {len(embeddable)} articles...")
    db = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean", n_jobs=-1)
    labels = db.fit_predict(matrix)

    # Assign cluster IDs back to articles
    for article, label in zip(embeddable, labels):
        article.cluster_id = int(label)

    # Group into Cluster objects (exclude noise=-1)
    cluster_map: Dict[int, Cluster] = {}
    noise_articles: List[Article] = []

    for article, label in zip(embeddable, labels):
        if label == -1:
            noise_articles.append(article)
        else:
            if label not in cluster_map:
                cluster_map[label] = Cluster(cluster_id=label)
            cluster_map[label].articles.append(article)

    clusters = list(cluster_map.values())
    logger.info(f"Found {len(clusters)} clusters, {len(noise_articles)} singleton/noise articles")

    # --- Top Cited: sort clusters by unique source count (desc), then avg relevance ---
    clusters_sorted = sorted(
        clusters,
        key=lambda c: (c.unique_sources, c.avg_relevance),
        reverse=True,
    )

    # --- Top Blindspots ---
    # Candidates: noise articles + single-source clusters (dominated by one source)
    blindspot_candidates: List[Article] = []

    # Noise articles (singletons) with high relevance
    for art in noise_articles:
        if art.relevance_score >= blindspot_min:
            blindspot_candidates.append(art)

    # Single-source clusters with high avg relevance
    for cluster in clusters:
        if cluster.unique_sources == 1 and cluster.avg_relevance >= blindspot_min:
            blindspot_candidates.append(cluster.best_article)

    # Sort by relevance score
    blindspot_candidates.sort(key=lambda a: a.relevance_score, reverse=True)

    # Remove duplicates (same url)
    seen_urls: set = set()
    unique_blindspots: List[Article] = []
    for art in blindspot_candidates:
        if art.url not in seen_urls:
            unique_blindspots.append(art)
            seen_urls.add(art.url)

    top_cited = clusters_sorted[:top_cited_count]
    top_blindspots = unique_blindspots[:blindspot_count]

    logger.info(
        f"Top Cited: {len(top_cited)} clusters | "
        f"Top Blindspots: {len(top_blindspots)} articles"
    )

    return clusters_sorted, top_blindspots
