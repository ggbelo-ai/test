"""Telegram bot — card formatting and inline button callback handlers.

Sends theme cards and founder cards with inline keyboard buttons that
write partner decisions back to the Living Investment Memo.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from db import living_memo
from db.supabase_client import update_founder_decision, update_theme

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ------------------------------------------------------------------
# Card formatting
# ------------------------------------------------------------------

def format_theme_card(theme: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Format a theme into a Telegram message with inline buttons.

    Returns:
        Tuple of (message_text, inline_keyboard).
    """
    maturity_emoji = {
        "pre_commercial": "🔬",
        "early_commercial": "🛠",
        "accelerating": "🚀",
        "crowded": "🏪",
    }

    emoji = maturity_emoji.get(theme.get("signal_maturity", ""), "📊")
    novelty = theme.get("novelty_score", 0)
    novelty_bar = "█" * int(novelty * 10) + "░" * (10 - int(novelty * 10))

    text = (
        f"{emoji} *New Theme Detected*\n\n"
        f"*{theme['label']}*\n\n"
        f"Novelty: `[{novelty_bar}]` {novelty:.0%}\n"
        f"Maturity: `{theme.get('signal_maturity', 'unknown')}`\n"
        f"Status: `{theme.get('status', 'emerging')}`\n"
    )

    if theme.get("signal_sources"):
        sources = theme["signal_sources"]
        if isinstance(sources, list):
            text += f"\nSources: {', '.join(str(s) for s in sources[:5])}\n"

    if theme.get("description"):
        text += f"\n_{theme['description'][:200]}_\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Deep-dive", callback_data=f"theme_deepdive:{theme['id']}"),
            InlineKeyboardButton("👀 Watch", callback_data=f"theme_watch:{theme['id']}"),
            InlineKeyboardButton("❌ Pass", callback_data=f"theme_pass:{theme['id']}"),
        ]
    ])

    return text, keyboard


def format_founder_card(founder: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Format a founder profile into a Telegram message with inline buttons.

    Returns:
        Tuple of (message_text, inline_keyboard).
    """
    score = founder.get("signal_score", 0)
    signals = founder.get("signals_detected", [])

    text = (
        f"👤 *High-Signal Founder Detected*\n\n"
        f"*{founder['name']}*\n\n"
        f"Signal Score: `{score}`\n"
        f"Signals: {', '.join(signals) if signals else 'N/A'}\n"
    )

    if founder.get("twitter_handle"):
        text += f"Twitter: @{founder['twitter_handle']}\n"
    if founder.get("github_username"):
        text += f"GitHub: {founder['github_username']}\n"
    if founder.get("draft_outreach"):
        text += f"\n💬 _Draft outreach:_\n_{founder['draft_outreach'][:300]}_\n"

    founder_id = founder.get("id", founder.get("founder_id", "unknown"))
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📧 Draft outreach", callback_data=f"founder_outreach:{founder_id}"),
            InlineKeyboardButton("👀 Watch", callback_data=f"founder_watch:{founder_id}"),
            InlineKeyboardButton("❌ Pass", callback_data=f"founder_pass:{founder_id}"),
        ]
    ])

    return text, keyboard


# ------------------------------------------------------------------
# Send functions
# ------------------------------------------------------------------

async def send_theme_card(theme: dict, chat_id: str | None = None) -> None:
    """Send a theme notification card to Telegram."""
    app = Application.builder().token(BOT_TOKEN).build()
    text, keyboard = format_theme_card(theme)
    async with app:
        await app.bot.send_message(
            chat_id=chat_id or CHAT_ID,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


async def send_founder_card(founder: dict, chat_id: str | None = None) -> None:
    """Send a founder notification card to Telegram."""
    app = Application.builder().token(BOT_TOKEN).build()
    text, keyboard = format_founder_card(founder)
    async with app:
        await app.bot.send_message(
            chat_id=chat_id or CHAT_ID,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


# ------------------------------------------------------------------
# Callback handlers (inline button presses)
# ------------------------------------------------------------------

async def handle_theme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses on theme cards."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, theme_id = data.split(":", 1)

    action_map = {
        "theme_deepdive": ("active", "Deep-diving into theme"),
        "theme_watch": ("emerging", "Watching theme"),
        "theme_pass": ("crowded", "Passed on theme"),
    }

    if action in action_map:
        new_status, response_text = action_map[action]
        update_theme(theme_id, status=new_status)
        living_memo.update_thesis(theme_id, status=new_status)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ {response_text}: {theme_id[:8]}...")


async def handle_founder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses on founder cards."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, founder_id = data.split(":", 1)

    action_map = {
        "founder_outreach": ("reach_out", "Drafting outreach for founder"),
        "founder_watch": ("watching", "Watching founder"),
        "founder_pass": ("pass", "Passed on founder"),
    }

    if action in action_map:
        decision, response_text = action_map[action]
        update_founder_decision(founder_id, decision)
        living_memo.update_watch_founder(founder_id, partner_decision=decision)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ {response_text}: {founder_id[:8]}...")


# ------------------------------------------------------------------
# Bot startup command
# ------------------------------------------------------------------

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "🔮 *Conviction Engine Bot*\n\n"
        "I'll send you theme and founder alerts with decision buttons.\n"
        f"Your chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown",
    )


def build_bot_application() -> Application:
    """Build and configure the Telegram bot application with all handlers."""
    app = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", handle_start))

    # Callback query handlers for inline buttons
    app.add_handler(CallbackQueryHandler(handle_theme_callback, pattern=r"^theme_"))
    app.add_handler(CallbackQueryHandler(handle_founder_callback, pattern=r"^founder_"))

    return app
