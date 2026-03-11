"""Orchestrator Agent — LangGraph-based central coordinator.

Routes tasks to sub-agents, merges outputs, maintains the Living Investment Memo,
and escalates high-conviction findings to partners via Telegram.

Wired as a LangGraph StateGraph with conditional routing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from db import living_memo
from db.supabase_client import get_theme, update_theme
from notifications.telegram import send_founder_card, send_theme_card

logger = logging.getLogger(__name__)

# Escalation thresholds
THEME_NOVELTY_TELEGRAM_THRESHOLD = 0.75
FOUNDER_SIGNAL_TELEGRAM_THRESHOLD = 40


# ------------------------------------------------------------------
# LangGraph State
# ------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """Shared state flowing through the orchestrator graph."""

    task_type: str  # 'new_theme', 'founder_alert'
    data: dict  # Input payload
    memo_updated: bool
    telegram_sent: bool
    market_map: dict | None
    error: str | None


# ------------------------------------------------------------------
# Graph Nodes
# ------------------------------------------------------------------

def classify_task(state: AgentState) -> AgentState:
    """Entry node — validate and classify the incoming task."""
    task_type = state.get("task_type", "")
    data = state.get("data", {})

    if task_type not in ("new_theme", "founder_alert"):
        return {**state, "error": f"Unknown task type: {task_type}"}

    logger.info("Orchestrator: classifying task_type=%s", task_type)
    return state


def update_memo_theme(state: AgentState) -> AgentState:
    """Update the Living Investment Memo with a new or updated theme."""
    theme = state["data"]
    theme_id = theme.get("id", "")

    existing = living_memo.get_thesis(theme_id)

    if existing:
        living_memo.update_thesis(
            theme_id,
            novelty_score=theme.get("novelty_score"),
            signal_maturity=theme.get("signal_maturity"),
        )
        logger.info("Updated existing thesis: %s", theme.get("label"))
    else:
        living_memo.add_thesis(
            theme_id=theme_id,
            label=theme.get("label", "Unknown"),
            novelty_score=theme.get("novelty_score", 0),
            signal_maturity=theme.get("signal_maturity", "pre_commercial"),
        )
        logger.info("Added new thesis to memo: %s", theme.get("label"))

    return {**state, "memo_updated": True}


def update_memo_founder(state: AgentState) -> AgentState:
    """Update the Living Investment Memo with a founder alert."""
    founder = state["data"]

    living_memo.add_watch_founder(
        name=founder["name"],
        signal_score=founder.get("signal_score", 0),
        likely_theme=founder.get("likely_theme_id"),
        recommended_action=founder.get("recommended_action", "watch"),
    )
    logger.info("Added founder to watch list: %s", founder.get("name"))

    return {**state, "memo_updated": True}


def send_telegram_theme(state: AgentState) -> AgentState:
    """Send a Telegram theme card if novelty exceeds threshold."""
    theme = state["data"]
    novelty = theme.get("novelty_score", 0)

    if novelty < THEME_NOVELTY_TELEGRAM_THRESHOLD:
        logger.info("Theme below Telegram threshold (%.2f < %.2f), skipping",
                     novelty, THEME_NOVELTY_TELEGRAM_THRESHOLD)
        return {**state, "telegram_sent": False}

    try:
        asyncio.get_event_loop().run_until_complete(send_theme_card(theme))
        logger.info("Sent Telegram theme card for '%s'", theme.get("label"))
        return {**state, "telegram_sent": True}
    except RuntimeError:
        # No event loop running — create one
        try:
            asyncio.run(send_theme_card(theme))
            return {**state, "telegram_sent": True}
        except Exception as exc:
            logger.error("Failed to send Telegram theme card: %s", exc)
            return {**state, "telegram_sent": False}
    except Exception as exc:
        logger.error("Failed to send Telegram theme card: %s", exc)
        return {**state, "telegram_sent": False}


def send_telegram_founder(state: AgentState) -> AgentState:
    """Send a Telegram founder card if signal score exceeds threshold."""
    founder = state["data"]
    score = founder.get("signal_score", 0)

    if score < FOUNDER_SIGNAL_TELEGRAM_THRESHOLD:
        return {**state, "telegram_sent": False}

    try:
        asyncio.get_event_loop().run_until_complete(send_founder_card(founder))
        return {**state, "telegram_sent": True}
    except RuntimeError:
        try:
            asyncio.run(send_founder_card(founder))
            return {**state, "telegram_sent": True}
        except Exception as exc:
            logger.error("Failed to send Telegram founder card: %s", exc)
            return {**state, "telegram_sent": False}
    except Exception as exc:
        logger.error("Failed to send Telegram founder card: %s", exc)
        return {**state, "telegram_sent": False}


def run_market_cartographer(state: AgentState) -> AgentState:
    """Trigger Market Cartographer for a new theme."""
    theme = state["data"]
    theme_id = theme.get("id")
    label = theme.get("label", "")

    if not theme_id:
        logger.warning("No theme_id — skipping Market Cartographer")
        return {**state, "market_map": None}

    try:
        from agents.market_cartographer import build_market_map
        market_map = asyncio.run(build_market_map(theme_id, label))

        # Update memo with company count
        living_memo.update_thesis(theme_id, companies_tracked=market_map.company_count)
        logger.info("Market map built: %d companies tracked", market_map.company_count)

        return {**state, "market_map": {
            "company_count": market_map.company_count,
            "tam_estimate": market_map.tam_estimate,
            "tam_confidence": market_map.tam_confidence,
        }}
    except Exception as exc:
        logger.error("Market Cartographer failed for '%s': %s", label, exc)
        return {**state, "market_map": None}


# ------------------------------------------------------------------
# Conditional routing
# ------------------------------------------------------------------

def route_by_task_type(state: AgentState) -> str:
    """Route to the appropriate memo update node based on task type."""
    if state.get("error"):
        return "end"
    task_type = state.get("task_type", "")
    if task_type == "new_theme":
        return "update_memo_theme"
    elif task_type == "founder_alert":
        return "update_memo_founder"
    return "end"


def route_after_theme_memo(state: AgentState) -> str:
    """After theme memo update, proceed to Telegram and market mapping."""
    return "send_telegram_theme"


def route_after_founder_memo(state: AgentState) -> str:
    """After founder memo update, proceed to Telegram notification."""
    return "send_telegram_founder"


# ------------------------------------------------------------------
# Build the LangGraph
# ------------------------------------------------------------------

def build_orchestrator_graph() -> StateGraph:
    """Build and compile the orchestrator LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("classify_task", classify_task)
    graph.add_node("update_memo_theme", update_memo_theme)
    graph.add_node("update_memo_founder", update_memo_founder)
    graph.add_node("send_telegram_theme", send_telegram_theme)
    graph.add_node("send_telegram_founder", send_telegram_founder)
    graph.add_node("run_market_cartographer", run_market_cartographer)

    # Entry point
    graph.set_entry_point("classify_task")

    # Conditional routing after classification
    graph.add_conditional_edges(
        "classify_task",
        route_by_task_type,
        {
            "update_memo_theme": "update_memo_theme",
            "update_memo_founder": "update_memo_founder",
            "end": END,
        },
    )

    # Theme path: memo → telegram → market cartographer → end
    graph.add_edge("update_memo_theme", "send_telegram_theme")
    graph.add_edge("send_telegram_theme", "run_market_cartographer")
    graph.add_edge("run_market_cartographer", END)

    # Founder path: memo → telegram → end
    graph.add_edge("update_memo_founder", "send_telegram_founder")
    graph.add_edge("send_telegram_founder", END)

    return graph


# Compile the graph once at module level
_graph = build_orchestrator_graph()
orchestrator_app = _graph.compile()


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def route_task(task_type: str, data: dict) -> dict:
    """Route a task through the LangGraph orchestrator pipeline.

    Args:
        task_type: Type of task ('new_theme', 'founder_alert').
        data: Task data dict.

    Returns:
        Final state dict after graph execution.
    """
    initial_state: AgentState = {
        "task_type": task_type,
        "data": data,
        "memo_updated": False,
        "telegram_sent": False,
        "market_map": None,
        "error": None,
    }

    result = orchestrator_app.invoke(initial_state)
    logger.info(
        "Orchestrator complete: task=%s memo_updated=%s telegram=%s",
        task_type,
        result.get("memo_updated"),
        result.get("telegram_sent"),
    )
    return result
