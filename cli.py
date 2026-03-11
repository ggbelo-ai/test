"""CLI entry point for manually triggering agents and inspecting state.

Usage:
    python cli.py scan           — Run Horizon Scanner now
    python cli.py map <theme>    — Run Market Cartographer for a theme label
    python cli.py founders       — Run Founder Radar now
    python cli.py memo           — Print the current Living Investment Memo
    python cli.py themes         — List all themes in the knowledge graph
    python cli.py test-telegram  — Send a test Telegram message
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)


def cmd_scan(args: argparse.Namespace) -> None:
    """Run the Horizon Scanner."""
    from agents.horizon_scanner import scan_horizon
    from agents.orchestrator import route_task

    print("Running Horizon Scanner...")
    themes = scan_horizon()
    print(f"\nDiscovered {len(themes)} novel themes:\n")

    for t in themes:
        print(f"  [{t.signal_maturity}] {t.label} (novelty={t.novelty_score:.2f})")
        print(f"    Sources: {', '.join(t.signal_sources[:5])}")
        print()

        if not args.dry_run:
            route_task("new_theme", {
                "id": None,
                "label": t.label,
                "novelty_score": t.novelty_score,
                "signal_maturity": t.signal_maturity,
                "signal_sources": t.signal_sources,
                "description": t.description,
            })


def cmd_map(args: argparse.Namespace) -> None:
    """Run the Market Cartographer for a given theme."""
    from agents.market_cartographer import build_market_map

    print(f"Building market map for: {args.theme}")
    market_map = asyncio.run(build_market_map(args.theme_id or "manual", args.theme))

    print(f"\nMarket Map Complete:")
    print(f"  Companies: {market_map.company_count}")
    print(f"  Early stage: {len(market_map.early_stage)}")
    print(f"  Growth stage: {len(market_map.growth_stage)}")
    print(f"  Incumbents: {len(market_map.incumbents)}")
    print(f"  TAM: {market_map.tam_estimate} (confidence: {market_map.tam_confidence})")


def cmd_founders(args: argparse.Namespace) -> None:
    """Run the Founder Radar."""
    from scheduler.tasks import _gather_tracked_profiles
    from agents.founder_radar import scan_founder, SIGNAL_SCORE_THRESHOLD
    from agents.orchestrator import route_task

    profiles = _gather_tracked_profiles()
    print(f"Scanning {len(profiles)} tracked profiles...\n")

    high_signal = []
    for p in profiles:
        result = scan_founder(
            name=p["name"],
            signals=p.get("signals", []),
            theme_id=p.get("theme_id"),
            twitter_handle=p.get("twitter_handle"),
            github_username=p.get("github_username"),
            linkedin_url=p.get("linkedin_url"),
        )
        if result.signal_score >= SIGNAL_SCORE_THRESHOLD:
            high_signal.append(result)
            if not args.dry_run:
                route_task("founder_alert", {
                    "name": result.name,
                    "signal_score": result.signal_score,
                    "signals_detected": result.signals_detected,
                    "likely_theme_id": result.likely_theme_id,
                    "recommended_action": result.recommended_action,
                    "draft_outreach": result.draft_outreach,
                })

    print(f"Found {len(high_signal)} high-signal founders:\n")
    for f in high_signal:
        print(f"  {f.name} — score={f.signal_score}, action={f.recommended_action}")
        print(f"    Signals: {', '.join(f.signals_detected)}")
        print()


def cmd_memo(args: argparse.Namespace) -> None:
    """Print the current Living Investment Memo."""
    from db.living_memo import get_memo

    memo = get_memo()
    print(json.dumps(memo, indent=2, default=str))


def cmd_themes(args: argparse.Namespace) -> None:
    """List themes in the knowledge graph."""
    from db.supabase_client import list_themes

    themes = list_themes(limit=args.limit)
    print(f"Themes ({len(themes)}):\n")
    for t in themes:
        novelty = t.get("novelty_score", 0) or 0
        print(f"  [{t.get('signal_maturity', '?'):17s}] {t['label'][:60]}")
        print(f"    Status: {t.get('status', '?')} | Novelty: {novelty:.2f} | ID: {t['id'][:8]}...")
        print()


def cmd_test_telegram(args: argparse.Namespace) -> None:
    """Send a test Telegram card."""
    from notifications.telegram import send_theme_card

    test_theme = {
        "id": "test-00000000",
        "label": "Test Theme — Conviction Engine Health Check",
        "novelty_score": 0.99,
        "signal_maturity": "early_commercial",
        "status": "emerging",
        "signal_sources": ["test:manual"],
        "description": "This is a test message to verify Telegram integration is working.",
    }

    print("Sending test Telegram theme card...")
    asyncio.run(send_theme_card(test_theme))
    print("Sent successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Conviction Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Run Horizon Scanner")
    scan_parser.add_argument("--dry-run", action="store_true", help="Don't route to orchestrator")

    # map
    map_parser = subparsers.add_parser("map", help="Run Market Cartographer")
    map_parser.add_argument("theme", help="Theme label to map")
    map_parser.add_argument("--theme-id", help="Theme UUID (optional)")

    # founders
    founders_parser = subparsers.add_parser("founders", help="Run Founder Radar")
    founders_parser.add_argument("--dry-run", action="store_true", help="Don't route to orchestrator")

    # memo
    subparsers.add_parser("memo", help="Print Living Investment Memo")

    # themes
    themes_parser = subparsers.add_parser("themes", help="List themes")
    themes_parser.add_argument("--limit", type=int, default=20, help="Max themes to show")

    # test-telegram
    subparsers.add_parser("test-telegram", help="Send test Telegram card")

    args = parser.parse_args()

    commands = {
        "scan": cmd_scan,
        "map": cmd_map,
        "founders": cmd_founders,
        "memo": cmd_memo,
        "themes": cmd_themes,
        "test-telegram": cmd_test_telegram,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
