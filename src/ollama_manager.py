"""
Ollama VRAM Manager.

Handles explicit model lifecycle to respect available VRAM:
  - preload(model):  warms the model into VRAM before batch queries
  - unload(model):   evicts the model from VRAM immediately (keep_alive=0)
  - loaded_models(): queries /api/ps for what is currently in VRAM
  - assert_only(model): ensures no other model is loaded before loading this one

Pipeline contract enforced in pipeline.py:
  Stage 2 (embed):   preload embedding_model → batch embed → unload embedding_model
  Stage 4 (analyze): preload completion_model → batch analyze → unload completion_model

  The two models NEVER overlap in VRAM.
"""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def loaded_models(base_url: str, timeout: int = 10) -> list[dict]:
    """
    Return list of models currently loaded in VRAM.
    Each entry: {"name": str, "size_vram": int, ...}
    """
    endpoint = f"{base_url.rstrip('/')}/api/ps"
    try:
        resp = requests.get(endpoint, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except Exception as e:
        logger.warning(f"Could not query Ollama /api/ps: {e}")
        return []


def _vram_summary(base_url: str) -> str:
    """Human-readable string of currently loaded models + VRAM usage."""
    models = loaded_models(base_url)
    if not models:
        return "(no models loaded)"
    parts = []
    for m in models:
        mb = m.get("size_vram", 0) // (1024 * 1024)
        parts.append(f"{m['name']} ({mb} MB VRAM)")
    return ", ".join(parts)


def preload(model: str, base_url: str, timeout: int = 30) -> bool:
    """
    Warm a model into VRAM by sending a no-op generate request.
    Uses keep_alive="10m" so Ollama holds it hot for the upcoming batch.

    Returns True on success.
    """
    logger.info(f"[VRAM] Pre-loading model: {model}")
    logger.info(f"[VRAM] Currently in VRAM: {_vram_summary(base_url)}")

    # For embedding models use /api/embeddings; for generative use /api/generate
    if _is_embedding_model(model, base_url):
        endpoint = f"{base_url.rstrip('/')}/api/embeddings"
        payload = {"model": model, "prompt": "warmup", "keep_alive": "10m"}
    else:
        endpoint = f"{base_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": "warmup",
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_predict": 1},
        }

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.info(f"[VRAM] ✓ {model} loaded. VRAM now: {_vram_summary(base_url)}")
        return True
    except Exception as e:
        logger.warning(f"[VRAM] Pre-load failed for {model}: {e}")
        return False


def unload(model: str, base_url: str, timeout: int = 15) -> bool:
    """
    Evict a model from VRAM immediately by sending keep_alive=0.
    Ollama interprets keep_alive=0 as "unload right after this request."

    Returns True on success.
    """
    logger.info(f"[VRAM] Unloading model: {model}")

    if _is_embedding_model(model, base_url):
        endpoint = f"{base_url.rstrip('/')}/api/embeddings"
        payload = {"model": model, "prompt": "", "keep_alive": 0}
    else:
        endpoint = f"{base_url.rstrip('/')}/api/generate"
        payload = {"model": model, "prompt": "", "stream": False, "keep_alive": 0}

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.info(f"[VRAM] ✓ {model} unloaded. VRAM now: {_vram_summary(base_url)}")
        return True
    except Exception as e:
        logger.warning(f"[VRAM] Unload failed for {model}: {e}")
        return False


def unload_all_except(keep_model: Optional[str], base_url: str, timeout: int = 15) -> None:
    """
    Unload every currently loaded model except keep_model.
    Call this before preloading a new model to guarantee no overlap.
    """
    for m in loaded_models(base_url):
        name = m.get("name", "")
        if keep_model and name == keep_model:
            continue
        logger.info(f"[VRAM] Evicting pre-existing model: {name}")
        unload(name, base_url, timeout)


def _is_embedding_model(model: str, base_url: str) -> bool:
    """
    Heuristic: if the model name contains known embedding identifiers,
    treat it as an embedding model and use /api/embeddings for lifecycle calls.
    """
    lower = model.lower()
    embedding_keywords = ["bge", "embed", "e5-", "nomic-embed", "mxbai-embed", "snowflake-arctic"]
    return any(kw in lower for kw in embedding_keywords)
