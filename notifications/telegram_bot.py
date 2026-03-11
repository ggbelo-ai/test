"""Telegram bot runner — standalone process for handling inline button callbacks.

Run via: python -m notifications.telegram_bot
"""

from __future__ import annotations

import logging
import sys

from notifications.telegram import build_bot_application

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the Telegram bot polling loop."""
    logger.info("Starting Conviction Engine Telegram bot...")
    app = build_bot_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
