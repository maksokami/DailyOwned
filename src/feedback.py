"""
Feedback CLI — the user-friendly way to teach the system your preferences.

Commands:
  python feedback.py --onboard           Interactive first-run setup wizard
  python feedback.py --like <url/text>   Add an article URL or snippet to liked pool
  python feedback.py --dislike <url>     Add to disliked list
  python feedback.py --interactive       Review recent articles interactively
  python feedback.py --show-profile      Show current preference summary
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
import yaml

# Ensure src/ is in path
sys.path.insert(0, str(Path(__file__).parent))

# Try to import rich for nice output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None


def _print(msg: str, style: str = ""):
    if RICH:
        console.print(msg, style=style)
    else:
        print(msg)


def _panel(title: str, content: str):
    if RICH:
        console.print(Panel(content, title=title, border_style="cyan"))
    else:
        print(f"\n{'='*50}\n{title}\n{'='*50}\n{content}\n")


def _prompt(text: str, default: str = "") -> str:
    if RICH:
        return Prompt.ask(text, default=default)
    else:
        result = input(f"{text} [{default}]: ").strip()
        return result if result else default


def _confirm(text: str, default: bool = True) -> bool:
    if RICH:
        return Confirm.ask(text, default=default)
    else:
        ans = input(f"{text} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        if not ans:
            return default
        return ans.startswith("y")


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        root = Path(__file__).parent.parent
        path = root / config_path
    with open(path) as f:
        return yaml.safe_load(f)


def add_liked(text: str, config: dict):
    liked_path = Path(config["paths"]["liked_articles"])
    liked_path.parent.mkdir(parents=True, exist_ok=True)
    with open(liked_path, "a") as f:
        f.write(f"{text.strip()}\n")
    _print(f"✓ Added to liked articles: {text[:80]}", style="green")


def add_disliked(text: str, config: dict):
    disliked_path = Path(config["paths"]["disliked_articles"])
    disliked_path.parent.mkdir(parents=True, exist_ok=True)
    with open(disliked_path, "a") as f:
        f.write(f"{text.strip()}\n")
    _print(f"✓ Added to disliked articles: {text[:80]}", style="yellow")


def show_profile(config: dict):
    liked_path = Path(config["paths"]["liked_articles"])
    disliked_path = Path(config["paths"]["disliked_articles"])

    liked = []
    if liked_path.exists():
        liked = [l for l in liked_path.read_text().splitlines() if l.strip() and not l.startswith("#")]

    disliked = []
    if disliked_path.exists():
        disliked = [l for l in disliked_path.read_text().splitlines() if l.strip() and not l.startswith("#")]

    _panel(
        "📊 Your Preference Profile",
        f"Liked articles/snippets: {len(liked)}\n"
        f"Disliked articles/snippets: {len(disliked)}\n\n"
        f"The more you add, the better the filter gets!\n"
        f"Run `python feedback.py --onboard` to add more."
    )

    if liked and RICH:
        table = Table(title="Recent Liked Entries", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Entry", style="cyan")
        for i, entry in enumerate(liked[-10:], 1):
            table.add_row(str(i), entry[:100])
        console.print(table)


ONBOARD_INTRO = """
╔══════════════════════════════════════════════════════════════╗
║   🔐  Security News Intelligence — First-Time Setup Wizard  ║
╚══════════════════════════════════════════════════════════════╝

This wizard helps you teach the system what security topics you care about.

The more examples you provide, the better the AI filter will work.
You can always add more later with:
  python feedback.py --like "article title or URL"

You can enter:
  • Article titles (e.g., "CVE-2024-1234 critical RCE in Apache")
  • Topic descriptions (e.g., "cloud IAM privilege escalation")
  • URLs of articles you've liked
  • Any keyword-rich phrases

Press Ctrl+C at any time to save and exit.
"""

EXAMPLE_TOPICS = [
    "Cloud security misconfigurations and CSPM findings",
    "AWS IAM privilege escalation techniques",
    "Azure Active Directory attacks and defense",
    "Kubernetes security vulnerabilities and hardening",
    "Supply chain attacks and software integrity",
    "Zero-day exploits and in-the-wild exploitation",
    "Ransomware tactics, techniques, and incident response",
    "OWASP Top 10 vulnerabilities and web application security",
    "Python security automation and API security",
    "Terraform and infrastructure-as-code security",
    "CSPM policy enforcement and cloud compliance",
    "Threat intelligence and APT group tracking",
    "Penetration testing methodologies and tools",
    "Detection engineering and SIEM rules",
    "Vulnerability management and patch prioritization",
]


def onboard(config: dict):
    _print(ONBOARD_INTRO, style="bold cyan" if RICH else "")

    liked_path = Path(config["paths"]["liked_articles"])
    liked_path.parent.mkdir(parents=True, exist_ok=True)

    # Check existing
    existing = []
    if liked_path.exists():
        existing = [l for l in liked_path.read_text().splitlines() if l.strip() and not l.startswith("#")]
        if existing:
            _print(f"\n📝 You already have {len(existing)} liked entries.\n", style="yellow")

    _print("Step 1: Quick Topic Selection", style="bold")
    _print("Select topics that interest you (just press Enter to skip any):\n")

    selected = []
    for i, topic in enumerate(EXAMPLE_TOPICS, 1):
        if RICH:
            ans = _confirm(f"  [{i:02d}] {topic}?", default=False)
        else:
            ans = _confirm(f"  [{i:02d}] {topic}?", default=False)
        if ans:
            selected.append(topic)

    if selected:
        with open(liked_path, "a") as f:
            f.write(f"\n# Added via onboard wizard on {datetime.now().strftime('%Y-%m-%d')}\n")
            for topic in selected:
                f.write(f"{topic}\n")
        _print(f"\n✓ Added {len(selected)} topics to your profile.\n", style="green")

    _print("\nStep 2: Paste Liked Article Titles or URLs", style="bold")
    _print("Enter one title or URL per line. Type 'done' or press Enter on empty line to finish.\n")

    custom_entries = []
    while True:
        try:
            entry = _prompt("  Article title/URL (or 'done' to finish)", default="done")
            if not entry or entry.lower() in ("done", "exit", "quit"):
                break
            custom_entries.append(entry.strip())
            _print(f"  ✓ Added", style="green")
        except (KeyboardInterrupt, EOFError):
            break

    if custom_entries:
        with open(liked_path, "a") as f:
            f.write(f"\n# Custom entries from onboard wizard\n")
            for entry in custom_entries:
                f.write(f"{entry}\n")
        _print(f"\n✓ Added {len(custom_entries)} custom entries.\n", style="green")

    total = len(existing) + len(selected) + len(custom_entries)
    _panel(
        "✅ Setup Complete",
        f"Your preference profile now has {total} entries.\n\n"
        f"Next steps:\n"
        f"  • Run the pipeline:  python src/pipeline.py --dry-run\n"
        f"  • Start the scheduler: python src/scheduler.py\n"
        f"  • Add more liked articles anytime:\n"
        f"    python src/feedback.py --like \"article title\"\n\n"
        f"The filter gets smarter with more examples!"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Preference feedback tool for the Security News Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python feedback.py --onboard
  python feedback.py --like "Critical RCE vulnerability in OpenSSH CVE-2024-6387"
  python feedback.py --like "https://krebsonsecurity.com/2024/07/new-openssh-bug/"
  python feedback.py --dislike "Consumer product recalls and physical security"
  python feedback.py --show-profile
        """,
    )
    parser.add_argument("--onboard", action="store_true", help="Run first-time setup wizard")
    parser.add_argument("--like", metavar="TEXT_OR_URL", help="Add an article to your liked pool")
    parser.add_argument("--dislike", metavar="TEXT_OR_URL", help="Add an article to your disliked list")
    parser.add_argument("--show-profile", action="store_true", help="Show current preference stats")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.onboard:
        onboard(config)
    elif args.like:
        add_liked(args.like, config)
    elif args.dislike:
        add_disliked(args.dislike, config)
    elif args.show_profile:
        show_profile(config)
    else:
        parser.print_help()
        _print("\n💡 Tip: Run --onboard to get started!", style="yellow")


if __name__ == "__main__":
    main()
