"""
Article dataclass used across all pipeline stages.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import numpy as np


@dataclass
class Article:
    title: str
    url: str
    summary: str
    source: str                          # RSS feed name
    published: Optional[datetime] = None
    full_text: str = ""
    tags: List[str] = field(default_factory=list)

    # Set by embedder
    embedding: Optional[np.ndarray] = None
    relevance_score: float = 0.0

    # Set by clusterer
    cluster_id: int = -1                 # -1 = noise / singleton

    # Set by analyzer
    cluster_label: str = ""
    cluster_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "source": self.source,
            "published": self.published.isoformat() if self.published else None,
            "tags": self.tags,
            "relevance_score": round(self.relevance_score, 4),
            "cluster_id": self.cluster_id,
            "cluster_label": self.cluster_label,
            "cluster_summary": self.cluster_summary,
        }
