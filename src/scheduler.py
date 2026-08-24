"""
Scheduler — runs the pipeline on a cron schedule using APScheduler.

Usage:
  python scheduler.py              # Start daemon (runs on configured schedule)
  python scheduler.py --run-now    # Run immediately, then start scheduler
  python scheduler.py --run-now --exit-after  # Run once and exit
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import load_config, run as run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scheduler")


def make_job(config: dict):
    """Return a zero-arg callable that runs the pipeline."""
    def job():
        logger.info("Scheduler triggered pipeline run.")
        try:
            run_pipeline(config)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
    return job


def main():
    parser = argparse.ArgumentParser(description="Security News scheduler")
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately before scheduling")
    parser.add_argument("--exit-after", action="store_true", help="Exit after the immediate run (no scheduling)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode (no git push)")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    cron_expr = config["schedule"]["cron"]
    tz = config["schedule"].get("timezone", "UTC")

    if args.run_now:
        logger.info("Running pipeline immediately (--run-now)...")
        run_pipeline(config, dry_run=args.dry_run)
        if args.exit_after:
            logger.info("--exit-after set. Exiting.")
            return

    # Parse cron expression: "0 7 * * *" → minute=0, hour=7, ...
    cron_parts = cron_expr.split()
    if len(cron_parts) != 5:
        logger.error(f"Invalid cron expression in config: '{cron_expr}'")
        sys.exit(1)

    minute, hour, day, month, day_of_week = cron_parts
    trigger = CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=tz,
    )

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(make_job(config), trigger=trigger, id="security_digest", name="Daily Security Digest")

    logger.info(f"Scheduler started. Cron: '{cron_expr}' ({tz})")
    logger.info(f"Next run: {scheduler.get_jobs()[0].next_run_time}")
    logger.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
