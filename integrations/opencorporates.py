"""OpenCorporates free tier integration — company registration data lookup."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

OPENCORPORATES_API = "https://api.opencorporates.com/v0.4"


@dataclass
class OpenCorpCompany:
    """A company record from OpenCorporates."""

    name: str
    jurisdiction: str
    company_number: str
    incorporation_date: str | None = None
    company_type: str = ""
    status: str = ""
    registered_address: str = ""
    url: str = ""
    source: str = "opencorporates"
    metadata: dict = field(default_factory=dict)


def search_opencorporates(
    query: str,
    jurisdiction: str | None = None,
    max_results: int = 30,
) -> list[OpenCorpCompany]:
    """Search OpenCorporates free tier for companies matching a query.

    Note: Free tier is rate-limited and returns limited fields.

    Args:
        query: Company name or keyword search.
        jurisdiction: Two-letter jurisdiction code (e.g. 'us_ca', 'gb').
        max_results: Maximum results to return.

    Returns:
        List of OpenCorpCompany objects.
    """
    params: dict = {"q": query, "per_page": min(max_results, 30)}
    if jurisdiction:
        params["jurisdiction_code"] = jurisdiction

    url = f"{OPENCORPORATES_API}/companies/search"
    companies: list[OpenCorpCompany] = []

    try:
        resp = httpx.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("results", {}).get("companies", []):
            company = item.get("company", {})
            companies.append(
                OpenCorpCompany(
                    name=company.get("name", ""),
                    jurisdiction=company.get("jurisdiction_code", ""),
                    company_number=company.get("company_number", ""),
                    incorporation_date=company.get("incorporation_date"),
                    company_type=company.get("company_type", ""),
                    status=company.get("current_status", ""),
                    registered_address=company.get("registered_address_in_full", ""),
                    url=company.get("opencorporates_url", ""),
                )
            )

    except httpx.HTTPError as exc:
        logger.error("OpenCorporates search failed: %s", exc)

    logger.info("OpenCorporates search for '%s' returned %d results", query, len(companies))
    return companies
