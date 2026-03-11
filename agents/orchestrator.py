"""Orchestrator Agent — central coordinator.

Routes tasks to sub-agents, merges outputs, maintains the Living Investment Memo,
and escalates high-conviction findings to partners via Telegram.
"""

from __future__ import annotations

import asyncio
import logging

from db import living_memo
from db.supabase_client import get_theme, update_theme
from notifications.telegram import send_founder_card, send_theme_card

logger = logging.getLogger(__name__)

# Escalation thresholds
THEME_NOVELTY_TELEGRAM_THRESHOLD = 0.75
FOUNDER_SIGNAL_TELEGRAM_THRESHOLD = 40


async def handle_new_theme(theme: dict) -> None:
    """Process a newly discovered theme from the Horizon Scanner.

    1. Determine if it confirms, extends, or contradicts an existing thesis
    2. Update the Living Investment Memo
    3. If novelty > 0.75, send Telegram alert
    4. Trigger Market Cartographer for landscape mapping

    Args:
        theme: Theme dict with id, label, novelty_score, signal_maturity, etc.
    """
    logger.info("Orchestrator: processing new theme '%s' (novelty=%.2f)",
                theme.get("label"), theme.get("novelty_score", 0))

    # Check if this extends an existing thesis
    existing = living_memo.get_thesis(theme.get("id", ""))

    if existing:
        # Update existing thesis
        living_memo.update_thesis(
            theme["id"],
            novelty_score=theme.get("novelty_score"),
            signal_maturity=theme.get("signal_maturity"),
        )
        logger.info("Updated existing thesis: %s", theme["label"])
    else:
        # Add new thesis to memo
        living_memo.add_thesis(
            theme_id=theme["id"],
            label=theme["label"],
            novelty_score=theme.get("novelty_score", 0),
            signal_maturity=theme.get("signal_maturity", "pre_commercial"),
        )
        logger.info("Added new thesis to memo: %s", theme["label"])

    # Escalate to Telegram if above threshold
    novelty = theme.get("novelty_score", 0)
    if novelty >= THEME_NOVELTY_TELEGRAM_THRESHOLD:
        try:
            await send_theme_card(theme)
            logger.info("Sent Telegram theme card for '%s'", theme["label"])
        except Exception as exc:
            logger.error("Failed to send Telegram theme card: %s", exc)

    # Trigger Market Cartographer
    from agents.market_cartographer import build_market_map
    try:
        market_map = await build_market_map(theme["id"], theme["label"])
        # Update memo with company count
        living_memo.update_thesis(
            theme["id"],
            companies_tracked=market_map.company_count,
        )
        logger.info("Market map built: %d companies tracked", market_map.company_count)
    except Exception as exc:
        logger.error("Market Cartographer failed for '%s': %s", theme["label"], exc)


async def handle_founder_alert(founder: dict) -> None:
    """Process a high-signal founder from the Founder Radar.

    1. Match founder expertise to active theses
    2. Add to watch list in Living Investment Memo
    3. If signal_score > 40, send Telegram alert

    Args:
        founder: Founder dict with name, signal_score, signals_detected, etc.
    """
    logger.info("Orchestrator: processing founder '%s' (score=%d)",
                founder.get("name"), founder.get("signal_score", 0))

    # Add to watch list
    living_memo.add_watch_founder(
        name=founder["name"],
        signal_score=founder.get("signal_score", 0),
        likely_theme=founder.get("likely_theme_id"),
        recommended_action=founder.get("recommended_action", "watch"),
    )

    # Escalate to Telegram
    if founder.get("signal_score", 0) >= FOUNDER_SIGNAL_TELEGRAM_THRESHOLD:
        try:
            await send_founder_card(founder)
            logger.info("Sent Telegram founder card for '%s'", founder["name"])
        except Exception as exc:
            logger.error("Failed to send Telegram founder card: %s", exc)


def route_task(task_type: str, data: dict) -> None:
    """Route a task to the appropriate handler.

    Args:
        task_type: Type of task ('new_theme', 'founder_alert').
        data: Task data dict.
    """
    if task_type == "new_theme":
        asyncio.run(handle_new_theme(data))
    elif task_type == "founder_alert":
        asyncio.run(handle_founder_alert(data))
    else:
        logger.warning("Unknown task type: %s", task_type)
