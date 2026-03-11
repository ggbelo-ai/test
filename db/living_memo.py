"""Living Investment Memo — CRUD operations.

The memo is a singleton JSONB document stored in the `living_memo` table.
It is the central state object continuously updated by the Orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.supabase_client import get_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Read
# ------------------------------------------------------------------

def get_memo() -> dict:
    """Return the current Living Investment Memo."""
    result = get_client().table("living_memo").select("memo").eq("id", 1).execute()
    if not result.data:
        return {"last_updated": None, "active_theses": [], "watch_list_founders": []}
    return result.data[0]["memo"]


# ------------------------------------------------------------------
# Write (full replace)
# ------------------------------------------------------------------

def _save_memo(memo: dict) -> dict:
    """Persist the full memo back to Supabase."""
    memo["last_updated"] = _now_iso()
    result = (
        get_client()
        .table("living_memo")
        .update({"memo": memo})
        .eq("id", 1)
        .execute()
    )
    return result.data[0]["memo"]


# ------------------------------------------------------------------
# Active theses
# ------------------------------------------------------------------

def add_thesis(
    theme_id: str,
    label: str,
    novelty_score: float,
    signal_maturity: str,
    companies_tracked: int = 0,
    watch_list_founders: int = 0,
    key_risks: list[str] | None = None,
    status: str = "emerging",
) -> dict:
    """Add a new thesis entry to the memo."""
    memo = get_memo()
    thesis = {
        "theme_id": theme_id,
        "label": label,
        "novelty_score": novelty_score,
        "signal_maturity": signal_maturity,
        "companies_tracked": companies_tracked,
        "watch_list_founders": watch_list_founders,
        "key_risks": key_risks or [],
        "status": status,
    }
    memo["active_theses"].append(thesis)
    return _save_memo(memo)


def update_thesis(theme_id: str, **fields: Any) -> dict:
    """Update fields on an existing thesis in the memo."""
    memo = get_memo()
    for thesis in memo["active_theses"]:
        if thesis["theme_id"] == theme_id:
            thesis.update(fields)
            break
    return _save_memo(memo)


def remove_thesis(theme_id: str) -> dict:
    """Remove a thesis from the memo."""
    memo = get_memo()
    memo["active_theses"] = [t for t in memo["active_theses"] if t["theme_id"] != theme_id]
    return _save_memo(memo)


def get_thesis(theme_id: str) -> dict | None:
    """Get a specific thesis by theme_id."""
    memo = get_memo()
    for thesis in memo["active_theses"]:
        if thesis["theme_id"] == theme_id:
            return thesis
    return None


# ------------------------------------------------------------------
# Watch-list founders
# ------------------------------------------------------------------

def add_watch_founder(
    name: str,
    signal_score: int,
    likely_theme: str | None = None,
    recommended_action: str = "watch",
    partner_decision: str | None = None,
) -> dict:
    """Add a founder to the watch list."""
    memo = get_memo()
    entry = {
        "name": name,
        "signal_score": signal_score,
        "likely_theme": likely_theme,
        "recommended_action": recommended_action,
        "partner_decision": partner_decision,
    }
    memo["watch_list_founders"].append(entry)
    return _save_memo(memo)


def update_watch_founder(name: str, **fields: Any) -> dict:
    """Update a watched founder's fields (e.g. partner_decision)."""
    memo = get_memo()
    for founder in memo["watch_list_founders"]:
        if founder["name"] == name:
            founder.update(fields)
            break
    return _save_memo(memo)


def remove_watch_founder(name: str) -> dict:
    """Remove a founder from the watch list."""
    memo = get_memo()
    memo["watch_list_founders"] = [
        f for f in memo["watch_list_founders"] if f["name"] != name
    ]
    return _save_memo(memo)
