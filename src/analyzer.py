"""
LLM-powered semantic analyzer & tagger.

Uses Ollama completions to:
  - Generate topic labels and tags for each cluster
  - Write synthesis summaries for Top Cited clusters
  - Explain blindspots
  - Dynamically assign tags to articles based on categories.yaml
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import List

import requests
import yaml

from clusterer import Cluster
from models import Article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Categories Loader
# ---------------------------------------------------------------------------
def _load_categories_text(config: dict) -> str:
    cat_path = Path(config["paths"].get("categories", "categories.yaml"))
    if not cat_path.exists():
        return "No categories defined."
    
    with open(cat_path) as f:
        data = yaml.safe_load(f)
    
    lines = []
    for c in data.get("categories", []):
        lines.append(f"- {c['name']}: {c['description']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ollama completion helper
# ---------------------------------------------------------------------------
def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks produced by deepseek-r1."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _complete(prompt: str, config: dict, max_tokens: int = 300) -> str:
    """Call Ollama /api/generate and return the response text."""
    base_url = config["ollama"]["base_url"].rstrip("/")
    model = config["ollama"]["completion_model"]
    timeout = config["ollama"].get("timeout", 120)

    endpoint = f"{base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.3,
        },
    }
    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return _strip_think_tags(raw).strip()
    except requests.exceptions.Timeout:
        logger.warning(f"Ollama completion timeout for model {model}")
        return ""
    except Exception as e:
        logger.error(f"Ollama completion error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Cluster analysis
# ---------------------------------------------------------------------------
def _analyze_cluster(cluster: Cluster, config: dict, categories_text: str) -> None:
    articles_text = "\n".join(
        f"- [{a.source}] {a.title}: {a.summary[:200]}"
        for a in cluster.articles[:8]
    )
    sources_text = ", ".join(cluster.source_names)

    prompt = f"""You are a cybersecurity intelligence analyst. Analyze the following group of related security news articles.

Articles:
{articles_text}

Available Categories:
{categories_text}

Respond with ONLY a JSON object in this exact format:
{{
  "label": "A short 4-8 word topic label",
  "summary": "A 2-3 sentence synthesis of the story. What is happening? Why does it matter?",
  "impact": "High|Medium|Low",
  "tags": ["CategoryName1", "CategoryName2"]
}}"""

    response = _complete(prompt, config, max_tokens=400)

    try:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            cluster.label = data.get("label", f"Cluster #{cluster.cluster_id}")
            cluster.summary = data.get("summary", "")
            cluster.impact = data.get("impact", "Medium")
            tags = data.get("tags", [])
            # Assign tags to all articles in the cluster
            for a in cluster.articles:
                a.tags = tags
            return
    except (json.JSONDecodeError, AttributeError):
        pass

    cluster.label = f"Story: {cluster.articles[0].title[:60]}"
    cluster.summary = f"Covered by {cluster.unique_sources} sources."
    cluster.impact = "Medium"


def _analyze_blindspot(article: Article, config: dict, categories_text: str) -> None:
    prompt = f"""You are a cybersecurity intelligence analyst. Analyze this underreported article.

Title: {article.title}
Source: {article.source}
Summary: {article.summary[:500]}

Available Categories:
{categories_text}

Respond with ONLY a JSON object in this exact format:
{{
  "summary": "2-3 sentences explaining why this matters and why it might be underreported.",
  "tags": ["CategoryName1", "CategoryName2"]
}}"""

    response = _complete(prompt, config, max_tokens=300)
    
    try:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            article.cluster_summary = data.get("summary", "")
            article.cluster_label = "Blindspot"
            article.tags = data.get("tags", [])
            return
    except:
        pass

    article.cluster_summary = "Unique coverage — worth reviewing."
    article.cluster_label = "Blindspot"


def _tag_feed_articles(articles: List[Article], config: dict, categories_text: str) -> None:
    """Assign tags to general feed articles."""
    for i, article in enumerate(articles):
        # Skip if already tagged (e.g. by being part of a cluster)
        if article.tags:
            continue
            
        logger.info(f"  Tagging article {i+1}/{len(articles)}...")
        prompt = f"""Analyze this security article:
Title: {article.title}
Summary: {article.summary[:400]}

Available Categories:
{categories_text}

Respond with ONLY a JSON object (no markdown, just JSON) containing the 1-3 most relevant categories from the list above:
{{
  "tags": ["CategoryName1"]
}}"""
        response = _complete(prompt, config, max_tokens=150)
        try:
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                article.tags = data.get("tags", [])
        except:
            pass
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def analyze_clusters(
    top_cited_clusters: List[Cluster],
    top_blindspots: List[Article],
    feed_articles: List[Article],
    config: dict,
) -> None:
    """
    Analyze clusters, blindspots, and tag general feed articles in-place.
    """
    total = len(top_cited_clusters) + len(top_blindspots) + len(feed_articles)
    if total == 0:
        return

    logger.info(f"LLM Tasks: {len(top_cited_clusters)} clusters | {len(top_blindspots)} blindspots | {len(feed_articles)} feed articles")
    cat_text = _load_categories_text(config)

    for i, cluster in enumerate(top_cited_clusters):
        logger.info(f"  Analyzing Cluster {i+1}/{len(top_cited_clusters)}...")
        _analyze_cluster(cluster, config, cat_text)
        time.sleep(0.5)

    for i, article in enumerate(top_blindspots):
        logger.info(f"  Analyzing Blindspot {i+1}/{len(top_blindspots)}...")
        _analyze_blindspot(article, config, cat_text)
        time.sleep(0.5)

    if feed_articles:
        logger.info("  Tagging general feed articles...")
        _tag_feed_articles(feed_articles, config, cat_text)

    logger.info("LLM Analysis complete.")
