"""
GitHub Pages publisher.
Copies the rendered index.html into the local GitHub Pages repo and git-pushes it.
"""
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def publish(config: dict, dry_run: bool = False) -> bool:
    """
    Copy output/index.html to the GitHub Pages repo and push.

    Returns True on success, False on failure.
    """
    if not config["publish"].get("enabled", True):
        logger.info("Publishing disabled in config.")
        return True

    pages_repo = Path(config["paths"]["github_pages_repo"]).expanduser()
    output_html = Path(config["paths"]["output_html"])

    if not output_html.exists():
        logger.error(f"Output HTML not found: {output_html}")
        return False

    if not pages_repo.exists():
        logger.error(
            f"GitHub Pages repo not found at {pages_repo}. "
            "Run setup.sh or set the correct path in config.yaml."
        )
        return False

    # Copy HTML to docs/ folder for GitHub Pages
    docs_dir = pages_repo / "docs"
    docs_dir.mkdir(exist_ok=True)
    dest = docs_dir / "index.html"
    shutil.copy2(output_html, dest)
    logger.info(f"Copied {output_html} → {dest}")

    if dry_run:
        logger.info("DRY RUN: skipping git commit and push.")
        return True

    # Git operations
    date_str = datetime.now().strftime("%Y-%m-%d")
    commit_msg = config["publish"]["commit_message"].format(date=date_str)
    branch = config["publish"].get("branch", "main")

    def run_git(args: list) -> tuple[int, str, str]:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(pages_repo),
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    code, out, err = run_git(["add", "."])
    if code != 0:
        logger.error(f"git add failed: {err}")
        return False

    code, out, err = run_git(["commit", "-m", commit_msg])
    if code != 0:
        if "nothing to commit" in out or "nothing to commit" in err:
            logger.info("Nothing to commit — HTML unchanged since last publish.")
            return True
        logger.error(f"git commit failed: {err}")
        return False

    logger.info(f"Committed: {commit_msg}")

    code, out, err = run_git(["push", "origin", branch])
    if code != 0:
        logger.error(f"git push failed: {err}")
        return False

    logger.info(f"Successfully pushed to {branch}. GitHub Pages will update in ~30s.")
    return True
