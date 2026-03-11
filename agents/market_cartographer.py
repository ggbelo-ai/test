"""Agent 2 — Market Cartographer.

Takes an emerging theme and builds a structured market map — TAM estimates,
competitive landscape segmentation, and incumbent tracking.

Trigger: On-demand, called by Orchestrator when a new theme is confirmed as novel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from db.supabase_client import insert_company, link_company_to_theme
from integrations.edgar import (
    EdgarCompanyData,
    estimate_tam_from_comparables,
    fetch_company_revenue,
    search_edgar_companies,
)
from integrations.opencorporates import search_opencorporates
from integrations.yc_scraper import scrape_yc_companies

logger = logging.getLogger(__name__)


@dataclass
class MarketMap:
    """Structured market map for an emerging theme."""

    theme_id: str
    theme_label: str
    tam_estimate: float | None = None
    tam_confidence: str = "low"
    early_stage: list[dict] = field(default_factory=list)
    growth_stage: list[dict] = field(default_factory=list)
    incumbents: list[dict] = field(default_factory=list)
    company_count: int = 0
    metadata: dict = field(default_factory=dict)


async def build_market_map(theme_id: str, theme_label: str) -> MarketMap:
    """Build a comprehensive market map for a given theme.

    1. Scrape YC company list for early-stage companies
    2. Search OpenCorporates for registered companies
    3. Find public comparables via SEC EDGAR
    4. Estimate TAM from public company revenues
    5. Segment into early-stage, growth-stage, and incumbents

    Args:
        theme_id: UUID of the theme in the knowledge graph.
        theme_label: Human-readable theme label for search queries.

    Returns:
        MarketMap with segmented competitive landscape.
    """
    logger.info("Building market map for theme: %s", theme_label)

    # 1. Scrape YC companies
    yc_companies = await scrape_yc_companies(keywords=theme_label, max_results=30)
    logger.info("Found %d YC companies for '%s'", len(yc_companies), theme_label)

    # 2. Search OpenCorporates
    oc_companies = search_opencorporates(theme_label, max_results=20)
    logger.info("Found %d OpenCorporates results for '%s'", len(oc_companies), theme_label)

    # 3. Find public comparables via EDGAR
    edgar_results = search_edgar_companies(theme_label, max_results=5)
    public_comps: list[EdgarCompanyData] = []
    for result in edgar_results:
        if result.get("cik"):
            comp_data = fetch_company_revenue(result["cik"])
            if comp_data:
                public_comps.append(comp_data)

    logger.info("Found %d public comparables for '%s'", len(public_comps), theme_label)

    # 4. Estimate TAM
    tam_data = estimate_tam_from_comparables(public_comps)

    # 5. Segment companies and persist to knowledge graph
    early_stage = []
    growth_stage = []
    incumbents = []

    # Process YC companies (typically early-stage)
    for yc in yc_companies:
        company_data = {
            "name": yc.name,
            "description": yc.description,
            "batch": yc.batch,
            "url": yc.url,
            "location": yc.location,
            "source": "yc",
        }
        early_stage.append(company_data)

        # Persist to knowledge graph
        db_company = insert_company(
            name=yc.name,
            url=yc.url,
            stage="seed",
            source="yc",
            metadata={"batch": yc.batch, "description": yc.description},
        )
        link_company_to_theme(db_company["id"], theme_id)

    # Process OpenCorporates companies
    for oc in oc_companies:
        company_data = {
            "name": oc.name,
            "jurisdiction": oc.jurisdiction,
            "incorporation_date": oc.incorporation_date,
            "status": oc.status,
            "source": "opencorporates",
        }
        growth_stage.append(company_data)

        db_company = insert_company(
            name=oc.name,
            source="opencorporates",
            geography=oc.jurisdiction,
            metadata={"incorporation_date": oc.incorporation_date},
        )
        link_company_to_theme(db_company["id"], theme_id)

    # Process public comparables (incumbents)
    for comp in public_comps:
        incumbents.append({
            "name": comp.company_name,
            "cik": comp.cik,
            "revenue": comp.revenue,
            "revenue_year": comp.revenue_year,
            "source": "edgar",
        })

        db_company = insert_company(
            name=comp.company_name,
            source="edgar",
            stage="public",
            metadata={"cik": comp.cik, "revenue": comp.revenue},
        )
        link_company_to_theme(db_company["id"], theme_id)

    market_map = MarketMap(
        theme_id=theme_id,
        theme_label=theme_label,
        tam_estimate=tam_data.get("tam_estimate"),
        tam_confidence=tam_data.get("tam_confidence", "low"),
        early_stage=early_stage,
        growth_stage=growth_stage,
        incumbents=incumbents,
        company_count=len(early_stage) + len(growth_stage) + len(incumbents),
        metadata=tam_data,
    )

    logger.info(
        "Market map complete for '%s': %d companies (%d early, %d growth, %d incumbents), TAM confidence: %s",
        theme_label,
        market_map.company_count,
        len(early_stage),
        len(growth_stage),
        len(incumbents),
        market_map.tam_confidence,
    )

    return market_map
