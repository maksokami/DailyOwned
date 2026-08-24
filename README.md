# ⬡ Security News Intelligence System

> Daily cybersecurity news digest — filtered by your interests, analyzed by AI, published to GitHub Pages automatically.


---

## Architecture

```
[RSS Feeds (25+ sources)]
        │
        ▼  feedparser
[Candidate Articles]  ──── lookback window filter (24h default)
        │
        ▼  Ollama: qllama/bge-m3:q8_0 embeddings
[Embedding & Cosine Similarity Filter]
   • Embeds liked_articles.txt → preference centroid
   • Scores every article vs. centroid
   • Drops articles below relevance_threshold (default: 0.45)
        │
        ▼  scikit-learn DBSCAN clustering
[Topic Cluster Analysis]
   ├──► Top Cited      (clusters with most unique sources)
   └──► Top Blindspots (high relevance score, low/single source)
        │
        ▼  Ollama: deepseek-r1:8b completions
[LLM Semantic Analysis]
   • Cluster topic labels
   • 2-3 sentence synthesis summaries
   • Impact ratings (High / Medium / Low)
   • Blindspot explanations
        │
        ▼  Jinja2 + Tailwind CSS
[index.html Generation]
        │
        ▼  git add / commit / push
[GitHub Pages → maksokami.github.io/DailyOwned]
        │
        ▼  APScheduler cron
[Runs daily at 7:00 AM CST (configurable)]
```

**VRAM usage**
Stage 1: Fetch RSS              ← no GPU
Stage 2: Embed + Filter
  ├─ unload_all_except(None)    ← evict any stale model from previous session
  ├─ preload(bge-m3)            ← warm into VRAM, log /api/ps state
  ├─ batch embed (keep_alive=10m, model stays hot)
  └─ unload(bge-m3)             ← VRAM free
Stage 3: DBSCAN cluster         ← CPU only, no VRAM
Stage 4: LLM Analysis
  ├─ preload(deepseek-r1:8b)    ← bge-m3 already gone, clean load
  ├─ batch completions (keep_alive=10m)
  └─ unload(deepseek-r1:8b)     ← VRAM returned to system
Stage 5: Render HTML            ← CPU only
Stage 6: Git push               ← no GPU

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally with these models:
  - `qllama/bge-m3:q8_0` (embeddings — already installed)
  - `deepseek-r1:8b` (analysis — already installed)
- SSH key configured for GitHub (`ssh -T git@github.com` should succeed)

### 2. Setup

```bash
cd /home/youruser/pathtotherepo
chmod +x setup.sh run.sh
./setup.sh
```

The setup script will:
- Create a Python virtual environment (`.venv/`)
- Install all dependencies
- Check Ollama connectivity
- Clone and clear the DailyOwned GitHub Pages repo
- Guide you through the onboarding wizard

### 3. Seed Your Preferences

This is the most important step. The more examples you give, the better the filter:

```bash
source .venv/bin/activate

# Interactive wizard (recommended for first run)
python src/feedback.py --onboard

# Or add individual articles/topics
python src/feedback.py --like "CVE-2024-6387 RegreSSHion OpenSSH RCE"
python src/feedback.py --like "Cloud IAM privilege escalation misconfigured roles"
python src/feedback.py --like "https://krebsonsecurity.com/2024/07/openssh-flaw/"
```

### 4. Test Run (No Publishing)

```bash
python src/pipeline.py --dry-run
# Opens output/index.html — inspect it in your browser
```

Fast test without LLM (no Ollama calls for analysis, just fetch + embed + render):
```bash
python src/pipeline.py --dry-run --no-llm
```

### 5. Full Run (Publish to GitHub Pages)

```bash
python src/pipeline.py
# Generates HTML and pushes to GitHub Pages
```

### 6. Start the Daily Scheduler

```bash
# Runs in foreground — use systemd or tmux for background
python src/scheduler.py

# Or run once immediately, then keep scheduling
python src/scheduler.py --run-now
```

---

## File Structure

```
therepo/
├── config.yaml           ← 🔧 All settings (feeds, schedule, thresholds)
├── feeds.yaml            ← 📡 RSS feed definitions (add/remove sources here)
├── liked_articles.txt    ← 💚 Your interest profile (one entry per line)
├── disliked_articles.txt ← Auto-managed by feedback.py
├── requirements.txt
├── setup.sh              ← One-time setup
├── run.sh                ← Quick launcher
├── README.md
├── src/
│   ├── pipeline.py       ← Main orchestrator (run this)
│   ├── fetcher.py        ← RSS feed ingestion
│   ├── embedder.py       ← Ollama embedding + similarity filter
│   ├── clusterer.py      ← DBSCAN topic clustering
│   ├── analyzer.py       ← LLM synthesis (deepseek-r1)
│   ├── renderer.py       ← Jinja2 HTML generation
│   ├── publisher.py      ← Git push to GitHub Pages
│   ├── feedback.py       ← Preference feedback CLI
│   ├── scheduler.py      ← APScheduler cron daemon
│   └── models.py         ← Article dataclass
├── templates/
│   └── index.html.j2     ← HTML template (Tailwind dark theme)
├── output/
│   └── index.html        ← Generated HTML (gitignored)
├── memory/               ← Future: cached embeddings
└── systemd/
    └── llm-cs-news.service  ← Run as a background service
```

---

## Configuration

Edit [`config.yaml`](config.yaml) to customize everything:

| Key | Default | Description |
|-----|---------|-------------|
| `ollama.embedding_model` | `qllama/bge-m3:q8_0` | Model for article embeddings |
| `ollama.completion_model` | `deepseek-r1:8b` | Model for LLM summaries |
| `relevance_threshold` | `0.45` | Min cosine similarity to pass filter (0–1) |
| `cluster_eps` | `0.35` | DBSCAN cluster tightness (lower = tighter) |
| `top_cited_count` | `5` | Number of Top Cited clusters to show |
| `blindspot_min_score` | `0.65` | Min relevance for blindspot candidates |
| `schedule.cron` | `0 7 * * *` | Daily at 7 AM |
| `schedule.timezone` | `America/NewYork` | Your timezone |
| `html.lookback_hours` | `24` | How far back to look for articles |

---

## Teaching the System (Feedback Loop)

The filter improves every time you add examples:

```bash
# Add liked article (URL or title)
python src/feedback.py --like "article title or URL"

# Add disliked article  
python src/feedback.py --dislike "topic or URL"

# Run onboarding wizard again
python src/feedback.py --onboard

# View your current profile stats
python src/feedback.py --show-profile
```

**Tuning tips:**
- Too many irrelevant articles → raise `relevance_threshold` (e.g., 0.55)
- Missing articles you care about → lower `relevance_threshold` (e.g., 0.35) or add more liked entries
- Too many singletons (no clusters) → raise `cluster_eps` (e.g., 0.45)
- Clusters too broad → lower `cluster_eps` (e.g., 0.25)

---

## Adding RSS Feeds

Edit [`feeds.yaml`](feeds.yaml):

```yaml
feeds:
  - name: "My Custom Source"
    url: "https://example.com/rss.xml"
    tags: [cloud, kubernetes]
```

---

## Running as a Background Service (systemd)

```bash
# Install the service
sudo cp systemd/llm-cs-news.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable llm-cs-news
sudo systemctl start llm-cs-news

# Check status
sudo systemctl status llm-cs-news
journalctl -u llm-cs-news -f
```

---

## GitHub Pages Setup Notes

The pipeline pushes `output/index.html` to the `DailyOwned` repo's `main` branch.

Make sure:
1. The repo has GitHub Pages enabled (Settings → Pages → Deploy from `main` branch, root `/`)
2. Your SSH key is added to GitHub and `ssh -T git@github.com` succeeds
3. The local clone path matches `paths.github_pages_repo` in `config.yaml`


---

## Models & Resources

| Component | Model | Size | Purpose |
|-----------|-------|------|---------|
| Embeddings | `qllama/bge-m3:q8_0` | 634 MB | Article vectorization & similarity |
| Analysis | `deepseek-r1:8b` | 5.2 GB | Topic labels, summaries, blindspot explanations |

To switch to a more powerful analysis model:
```yaml
# config.yaml
ollama:
  completion_model: "deepseek-r1:32b"  # better quality, slower
```
