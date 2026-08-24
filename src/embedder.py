"""
Embedding engine using Ollama's local API.

Uses the configured embedding model (qllama/bge-m3:q8_0 by default) to:
  1. Embed all articles from the liked-articles pool → compute centroid
  2. Embed each candidate article
  3. Score candidates via cosine similarity vs. the liked-pool centroid
  4. Filter out articles below the relevance_threshold
"""
import json
import logging
import math
from pathlib import Path
from typing import List, Optional

import numpy as np
import requests

from models import Article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ollama embedding helpers
# ---------------------------------------------------------------------------

def _embed_text(text: str, model: str, base_url: str, timeout: int) -> Optional[np.ndarray]:
    """Call Ollama /api/embeddings and return a numpy vector, or None on error.

    keep_alive="10m" tells Ollama to hold the model hot for 10 minutes.
    This prevents the model from being auto-evicted mid-batch.
    The pipeline orchestrator (pipeline.py) is responsible for the explicit
    unload call after the entire embedding stage completes.
    """
    endpoint = f"{base_url.rstrip('/')}/api/embeddings"
    try:
        resp = requests.post(
            endpoint,
            json={"model": model, "prompt": text, "keep_alive": "10m"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        vec = np.array(data["embedding"], dtype=np.float32)
        return vec
    except requests.exceptions.Timeout:
        logger.warning("Ollama embedding timeout for text snippet")
        return None
    except Exception as e:
        logger.error(f"Ollama embedding error: {e}")
        return None


def _embed_batch(texts: List[str], model: str, base_url: str, timeout: int) -> List[Optional[np.ndarray]]:
    """Embed a list of texts. Returns a list of vectors (or None for failures)."""
    results = []
    for i, text in enumerate(texts):
        if i % 10 == 0 and i > 0:
            logger.info(f"  Embedded {i}/{len(texts)} texts...")
        vec = _embed_text(text, model, base_url, timeout)
        results.append(vec)
    return results


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


# ---------------------------------------------------------------------------
# Liked-pool centroid
# ---------------------------------------------------------------------------

def _load_liked_pool(liked_path: Path) -> List[str]:
    """
    Load liked article titles/snippets from liked_articles.txt.
    Lines starting with # are comments. Blank lines are ignored.
    Each non-comment line is treated as a piece of text to embed.
    """
    if not liked_path.exists():
        return []
    texts = []
    with open(liked_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                texts.append(line)
    return texts


def build_liked_centroid(config: dict) -> Optional[np.ndarray]:
    """
    Build the embedding centroid from the liked articles pool.
    Returns None if the pool is empty (no filtering will occur).
    """
    liked_path = Path(config["paths"]["liked_articles"])
    liked_texts = _load_liked_pool(liked_path)

    if not liked_texts:
        logger.warning(
            "liked_articles.txt is empty. All articles will pass the filter. "
            "Run `python feedback.py --onboard` to seed your preferences."
        )
        return None

    model = config["ollama"]["embedding_model"]
    base_url = config["ollama"]["base_url"]
    timeout = config["ollama"].get("timeout", 120)

    logger.info(f"Embedding {len(liked_texts)} liked articles to build preference centroid...")
    vecs = _embed_batch(liked_texts, model, base_url, timeout)
    valid = [v for v in vecs if v is not None]

    if not valid:
        logger.error("Could not embed any liked articles. Check Ollama connection.")
        return None

    centroid = np.mean(np.stack(valid), axis=0)
    logger.info(f"Built preference centroid from {len(valid)} liked articles.")
    return centroid


# ---------------------------------------------------------------------------
# Main filter function
# ---------------------------------------------------------------------------

def embed_and_filter(
    articles: List[Article],
    config: dict,
    liked_centroid: Optional[np.ndarray],
) -> List[Article]:
    """
    Embed each article and compute its relevance score vs the liked centroid.
    Filters out articles below config['relevance_threshold'].

    If liked_centroid is None (empty pool), all articles pass with score 0.5.
    """
    if not articles:
        return []

    model = config["ollama"]["embedding_model"]
    base_url = config["ollama"]["base_url"]
    timeout = config["ollama"].get("timeout", 120)
    threshold = config.get("relevance_threshold", 0.45)

    # Build input texts: title + summary for richer signal
    texts = [f"{a.title}. {a.summary[:500]}" for a in articles]

    logger.info(f"Embedding {len(articles)} candidate articles...")
    vecs = _embed_batch(texts, model, base_url, timeout)

    filtered: List[Article] = []
    skipped = 0

    for article, vec in zip(articles, vecs):
        if vec is None:
            skipped += 1
            continue

        article.embedding = vec

        if liked_centroid is None:
            article.relevance_score = 0.5
            filtered.append(article)
        else:
            score = _cosine_similarity(vec, liked_centroid)
            article.relevance_score = score
            if score >= threshold:
                filtered.append(article)
            else:
                logger.debug(f"Filtered out (score={score:.3f}): {article.title[:60]}")

    logger.info(
        f"Filter: {len(filtered)}/{len(articles)} articles passed "
        f"(threshold={threshold}, skipped={skipped} due to embed errors)"
    )
    return filtered
