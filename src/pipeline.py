"""
Main pipeline orchestrator.

Runs all stages in order:
  1. Fetch RSS articles
  2. Embed + filter by liked-pool similarity
  3. Cluster into topics
  4. Analyze with LLM
  5. Render HTML
  6. Publish to GitHub Pages

Usage:
  python pipeline.py              # full run
  python pipeline.py --dry-run    # skip git push, print summary
  python pipeline.py --no-llm     # skip LLM analysis (faster, no summaries)
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

# Ensure src/ is on the path when running directly
sys.path.insert(0, str(Path(__file__).parent))

from fetcher import fetch_articles
from embedder import build_liked_centroid, embed_and_filter
from clusterer import cluster_articles
from analyzer import analyze_clusters
from renderer import render_html
from publisher import publish
import ollama_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        # Try relative to project root
        root = Path(__file__).parent.parent
        path = root / config_path
    with open(path) as f:
        return yaml.safe_load(f)


def run(config: dict, dry_run: bool = False, no_llm: bool = False) -> dict:
    """
    Execute the full pipeline. Returns a summary dict.

    VRAM contract:
      Stage 2: embedding_model is pre-warmed → batch embeds → explicitly unloaded
      Stage 4: completion_model is pre-warmed → batch analyses → explicitly unloaded
      The two models NEVER occupy VRAM at the same time.
    """
    t_start = time.time()
    base_url = config["ollama"]["base_url"]
    embed_model = config["ollama"]["embedding_model"]
    completion_model = config["ollama"]["completion_model"]

    logger.info("=" * 60)
    logger.info("Security News Intelligence Pipeline — Starting")
    logger.info("=" * 60)

    # Stage 1: Fetch
    logger.info("\n[1/6] Fetching RSS feeds...")
    articles = fetch_articles(config)
    if not articles:
        logger.warning("No articles fetched. Check feeds.yaml and network.")
        return {"status": "no_articles"}

    # Stage 2: Embed + Filter
    # ── VRAM: evict anything loaded, then pre-warm the embedding model ──────
    logger.info(f"\n[2/6] Building preference model and filtering {len(articles)} articles...")
    ollama_manager.unload_all_except(keep_model=None, base_url=base_url)
    ollama_manager.preload(embed_model, base_url)

    liked_centroid = build_liked_centroid(config)
    filtered = embed_and_filter(articles, config, liked_centroid)

    # ── VRAM: embedding done — evict the embedding model now ────────────────
    ollama_manager.unload(embed_model, base_url)

    if not filtered:
        logger.warning(
            "No articles passed the relevance filter. "
            "Try lowering relevance_threshold in config.yaml, or add more liked articles."
        )
        return {"status": "no_filtered"}

    # Stage 3: Cluster (CPU-only — no VRAM needed)
    logger.info(f"\n[3/6] Clustering {len(filtered)} filtered articles...")
    top_cited_count = config.get("top_cited_count", 5)
    clusters, blindspots = cluster_articles(filtered, config)
    top_cited = clusters[:top_cited_count]

    # Figure out the general feed articles before rendering, so we can tag them
    max_feed = config["html"].get("max_feed_articles", 40)
    feed_candidates = sorted(filtered, key=lambda a: a.relevance_score, reverse=True)
    
    featured_urls = set()
    for c in top_cited:
        for a in c.articles: featured_urls.add(a.url)
    for a in blindspots:
        featured_urls.add(a.url)
        
    feed_articles = [a for a in feed_candidates if a.url not in featured_urls][:max_feed]

    # Stage 4: LLM Analysis & Tagging
    # ── VRAM: pre-warm completion model (embedding model already unloaded) ──
    if no_llm:
        logger.info("\n[4/6] Skipping LLM analysis (--no-llm flag)")
        for c in top_cited:
            c.label = f"Topic: {c.best_article.title[:50]}"
            c.summary = f"Reported by {c.unique_sources} sources: {', '.join(c.source_names)}"
        for a in blindspots:
            a.cluster_summary = "Unique coverage — limited cross-source overlap."
    else:
        logger.info(f"\n[4/6] Analyzing and tagging...")
        ollama_manager.preload(completion_model, base_url)
        analyze_clusters(top_cited, blindspots, feed_articles, config)
        # ── VRAM: analysis done — unload completion model ───────────────────
        ollama_manager.unload(completion_model, base_url)

    # Stage 5: Render HTML (CPU-only)
    logger.info("\n[5/6] Rendering HTML...")
    # Pass feed_articles directly since we already sliced them
    render_html(top_cited, blindspots, feed_articles, config)

    # Stage 6: Publish
    logger.info(f"\n[6/6] Publishing {'(DRY RUN)' if dry_run else ''}...")
    success = publish(config, dry_run=dry_run)

    elapsed = time.time() - t_start
    summary = {
        "status": "success" if success else "publish_failed",
        "articles_fetched": len(articles),
        "articles_filtered": len(filtered),
        "clusters": len(clusters),
        "top_cited": len(top_cited),
        "blindspots": len(blindspots),
        "elapsed_seconds": round(elapsed, 1),
    }

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Complete")
    logger.info(f"  Fetched:   {summary['articles_fetched']} articles")
    logger.info(f"  Filtered:  {summary['articles_filtered']} (relevance threshold)")
    logger.info(f"  Clusters:  {summary['clusters']} topic groups")
    logger.info(f"  Top Cited: {summary['top_cited']}")
    logger.info(f"  Blindspots:{summary['blindspots']}")
    logger.info(f"  Time:      {summary['elapsed_seconds']}s")
    logger.info("=" * 60)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Security News Intelligence Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py                  # Full pipeline run
  python pipeline.py --dry-run        # Run everything, skip git push
  python pipeline.py --no-llm         # Fast run without LLM summaries
  python pipeline.py --config /path/to/config.yaml
        """,
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip git push")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM analysis")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    result = run(config, dry_run=args.dry_run, no_llm=args.no_llm)

    if result.get("status") not in ("success", None):
        sys.exit(1)


if __name__ == "__main__":
    main()
