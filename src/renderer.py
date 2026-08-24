"""
HTML renderer.
Uses Jinja2 to render the final index.html from templates/index.html.j2.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from clusterer import Cluster
from models import Article

logger = logging.getLogger(__name__)


def render_html(
    top_cited: List[Cluster],
    top_blindspots: List[Article],
    feed_articles: List[Article],
    config: dict,
) -> str:
    """
    Render the full HTML page and return it as a string.
    Also writes the output file.
    """
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )

    # Add custom filter for truncating text
    def truncate(text: str, length: int = 200) -> str:
        if len(text) <= length:
            return text
        return text[:length].rsplit(" ", 1)[0] + "…"

    env.filters["truncate_words"] = truncate

    template = env.get_template("index.html.j2")
    generated_at = datetime.now(timezone.utc).strftime("%A, %B %-d %Y at %H:%M UTC")

    # calculate total unique sources across all passed articles
    all_passed_articles = feed_articles + top_blindspots
    for c in top_cited:
        all_passed_articles.extend(c.articles)

    html = template.render(
        title=config["html"]["title"],
        tagline=config["html"]["tagline"],
        generated_at=generated_at,
        top_cited=top_cited,
        top_blindspots=top_blindspots,
        feed_articles=feed_articles,
        total_sources=len({a.source for a in all_passed_articles}),
        total_articles=len(all_passed_articles),
        lookback_hours=config["html"].get("lookback_hours", 24),
    )

    # Write output
    output_path = Path(config["paths"]["output_html"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Rendered HTML written to {output_path}")

    return html
