"""Supabase connection and query helpers for the Conviction Engine knowledge graph."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    """Return a singleton Supabase client."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
        _client = create_client(url, key)
    return _client


# ------------------------------------------------------------------
# Theme helpers
# ------------------------------------------------------------------

def insert_theme(
    label: str,
    novelty_score: float | None = None,
    signal_maturity: str | None = None,
    signal_sources: list | None = None,
    description: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    """Insert a new theme and return the created row."""
    data: dict[str, Any] = {"label": label}
    if novelty_score is not None:
        data["novelty_score"] = novelty_score
    if signal_maturity is not None:
        data["signal_maturity"] = signal_maturity
    if signal_sources is not None:
        data["signal_sources"] = signal_sources
    if description is not None:
        data["description"] = description
    if embedding is not None:
        data["embedding"] = embedding
    result = get_client().table("themes").insert(data).execute()
    return result.data[0]


def get_theme(theme_id: str) -> dict | None:
    """Fetch a single theme by ID."""
    result = get_client().table("themes").select("*").eq("id", theme_id).execute()
    return result.data[0] if result.data else None


def list_themes(status: str | None = None, limit: int = 50) -> list[dict]:
    """List themes, optionally filtered by status."""
    query = get_client().table("themes").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    return query.execute().data


def search_themes_by_embedding(embedding: list[float], limit: int = 5) -> list[dict]:
    """Find the most similar themes using pgvector cosine similarity via RPC."""
    result = get_client().rpc(
        "match_themes",
        {"query_embedding": embedding, "match_count": limit},
    ).execute()
    return result.data


def update_theme(theme_id: str, **fields) -> dict:
    """Update fields on an existing theme."""
    result = get_client().table("themes").update(fields).eq("id", theme_id).execute()
    return result.data[0]


# ------------------------------------------------------------------
# Company helpers
# ------------------------------------------------------------------

def insert_company(
    name: str,
    url: str | None = None,
    stage: str | None = None,
    sector: str | None = None,
    geography: str | None = None,
    founded_date: str | None = None,
    source: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Insert a new company."""
    data: dict[str, Any] = {"name": name}
    for key, val in [
        ("url", url), ("stage", stage), ("sector", sector),
        ("geography", geography), ("founded_date", founded_date),
        ("source", source), ("metadata", metadata),
    ]:
        if val is not None:
            data[key] = val
    result = get_client().table("companies").insert(data).execute()
    return result.data[0]


def get_company(company_id: str) -> dict | None:
    result = get_client().table("companies").select("*").eq("id", company_id).execute()
    return result.data[0] if result.data else None


def list_companies(source: str | None = None, limit: int = 50) -> list[dict]:
    query = get_client().table("companies").select("*").order("created_at", desc=True).limit(limit)
    if source:
        query = query.eq("source", source)
    return query.execute().data


# ------------------------------------------------------------------
# Founder helpers
# ------------------------------------------------------------------

def insert_founder(
    name: str,
    linkedin_url: str | None = None,
    twitter_handle: str | None = None,
    github_username: str | None = None,
    signal_score: int = 0,
    signals_detected: list[str] | None = None,
) -> dict:
    """Insert a new founder."""
    data: dict[str, Any] = {"name": name, "signal_score": signal_score}
    if linkedin_url:
        data["linkedin_url"] = linkedin_url
    if twitter_handle:
        data["twitter_handle"] = twitter_handle
    if github_username:
        data["github_username"] = github_username
    if signals_detected:
        data["signals_detected"] = signals_detected
    result = get_client().table("founders").insert(data).execute()
    return result.data[0]


def get_founder(founder_id: str) -> dict | None:
    result = get_client().table("founders").select("*").eq("id", founder_id).execute()
    return result.data[0] if result.data else None


def list_founders(min_score: int | None = None, limit: int = 50) -> list[dict]:
    query = get_client().table("founders").select("*").order("signal_score", desc=True).limit(limit)
    if min_score is not None:
        query = query.gte("signal_score", min_score)
    return query.execute().data


def update_founder_decision(founder_id: str, decision: str) -> dict:
    """Update partner decision on a founder (reach_out, watching, pass)."""
    result = (
        get_client()
        .table("founders")
        .update({"partner_decision": decision})
        .eq("id", founder_id)
        .execute()
    )
    return result.data[0]


# ------------------------------------------------------------------
# Relationship helpers
# ------------------------------------------------------------------

def link_founder_to_company(founder_id: str, company_id: str, role: str = "founder") -> dict:
    result = (
        get_client()
        .table("founder_founded_company")
        .upsert({"founder_id": founder_id, "company_id": company_id, "role": role})
        .execute()
    )
    return result.data[0]


def link_company_to_theme(company_id: str, theme_id: str, relevance_score: float = 1.0) -> dict:
    result = (
        get_client()
        .table("company_operates_in_theme")
        .upsert({"company_id": company_id, "theme_id": theme_id, "relevance_score": relevance_score})
        .execute()
    )
    return result.data[0]


def link_themes(theme_id_a: str, theme_id_b: str, similarity_score: float) -> dict:
    result = (
        get_client()
        .table("theme_related_to_theme")
        .upsert({
            "theme_id_a": theme_id_a,
            "theme_id_b": theme_id_b,
            "similarity_score": similarity_score,
        })
        .execute()
    )
    return result.data[0]


def link_founder_to_theme(founder_id: str, theme_id: str, confidence: float = 1.0) -> dict:
    result = (
        get_client()
        .table("founder_expert_in_theme")
        .upsert({"founder_id": founder_id, "theme_id": theme_id, "confidence": confidence})
        .execute()
    )
    return result.data[0]
