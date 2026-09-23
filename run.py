#!/usr/bin/env python3
"""Market Pulse - command line entry point.

Examples
--------
    python run.py --demo --dry-run     # bundled data, print to the terminal
    python run.py                      # live APIs, deliver on configured channels
    python run.py --schedule           # stay resident and run on a daily timer
    python run.py --export-only        # rebuild the dashboard snapshot only
    python run.py --test-channels      # send one short message to every channel
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from src.config import load_settings
from src.pipeline import AlertPipeline
from src.processing.models import Digest
from src.scheduler import Scheduler

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=LOG_FORMAT,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="market-pulse",
        description="Financial event and market news alert automation.",
    )
    parser.add_argument("--demo", action="store_true", help="use bundled sample data instead of live APIs")
    parser.add_argument("--dry-run", action="store_true", help="print the brief instead of sending it")
    parser.add_argument("--schedule", action="store_true", help="run continuously on the configured timer")
    parser.add_argument("--export-only", action="store_true", help="rebuild website/data/dashboard.json only")
    parser.add_argument("--test-channels", action="store_true", help="send a short test message to each channel")
    parser.add_argument("--no-dedupe", action="store_true", help="ignore the already-sent table")
    parser.add_argument("--config", default="config.yaml", help="path to the config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def print_banner(settings, mode: str) -> None:
    channels = ", ".join(settings.active_channels()) or "console"
    print("-" * 62)
    print(" Market Pulse · financial event & news alert automation")
    print(f" mode: {mode}   watchlist: {', '.join(settings.watchlist) or 'all'}")
    print(f" window: {settings.lookahead_days} days   channels: {channels}")
    print("-" * 62)


def test_channels(settings) -> int:
    from src.notifiers.email_notifier import EmailNotifier
    from src.notifiers.telegram_notifier import TelegramNotifier

    probe = Digest(generated_at=datetime.now(timezone.utc), watchlist=settings.watchlist, run_mode="channel test")
    failures = 0
    for notifier in (TelegramNotifier(settings), EmailNotifier(settings)):
        if not notifier.enabled:
            print(f"  {notifier.channel:<9} skipped - not enabled or missing credentials")
            continue
        result = notifier.send(probe)
        print(f"  {result}")
        failures += 0 if result.success else 1
    return failures


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    settings = load_settings(args.config)

    if args.test_channels:
        print_banner(settings, "channel test")
        return 1 if test_channels(settings) else 0

    if args.schedule:
        print_banner(settings, "scheduled")
        Scheduler(settings, args.demo, args.dry_run).serve_forever()
        return 0

    mode = "demo" if (args.demo or not settings.has_live_keys) else "live"
    print_banner(settings, mode + (" · dry run" if args.dry_run else ""))

    pipeline = AlertPipeline(settings, use_sample_data=args.demo, dry_run=args.dry_run)
    try:
        if args.export_only:
            raw_events, raw_news = pipeline.fetch()
            digest = pipeline.process(raw_events, raw_news)
            from src.export import export_dashboard

            path = export_dashboard(digest, pipeline.store, settings)
            print(f"\nDashboard snapshot written to {path}")
            return 0

        report = pipeline.run(skip_duplicates=not args.no_dedupe)
    finally:
        pipeline.close()

    print("\n" + report.summary())
    if report.error:
        print(f"error: {report.error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
