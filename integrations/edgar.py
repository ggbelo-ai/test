"""SEC EDGAR integration — fetch public company financials for TAM estimation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_COMPANY_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt={start}&enddt={end}&forms=10-K,10-Q,S-1"
EDGAR_FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={query}&forms=10-K"
EDGAR_COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Required by SEC: identify yourself
EDGAR_HEADERS = {
    "User-Agent": "ConvictionEngine/1.0 (research@example.com)",
    "Accept": "application/json",
}


@dataclass
class EdgarCompanyData:
    """Financial data extracted from SEC EDGAR filings."""

    cik: str
    company_name: str
    revenue: float | None = None
    revenue_year: int | None = None
    filing_type: str = ""
    sic_code: str = ""
    metadata: dict = field(default_factory=dict)


def search_edgar_companies(query: str, max_results: int = 10) -> list[dict]:
    """Search EDGAR full-text search for companies matching a theme.

    Args:
        query: Search term (e.g. 'neuromorphic computing').
        max_results: Max results to return.

    Returns:
        List of dicts with company filing info.
    """
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{query}%22&forms=10-K,S-1"
    results = []

    try:
        resp = httpx.get(url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for hit in data.get("hits", {}).get("hits", [])[:max_results]:
            source = hit.get("_source", {})
            results.append({
                "company_name": source.get("display_names", [None])[0] if source.get("display_names") else None,
                "cik": source.get("entity_id"),
                "form_type": source.get("form_type"),
                "filing_date": source.get("file_date"),
                "file_url": source.get("file_url"),
            })
    except httpx.HTTPError as exc:
        logger.error("EDGAR search failed: %s", exc)

    logger.info("EDGAR search for '%s' returned %d results", query, len(results))
    return results


def fetch_company_revenue(cik: str) -> EdgarCompanyData | None:
    """Fetch revenue data from SEC XBRL company facts API.

    Args:
        cik: SEC CIK number (will be zero-padded to 10 digits).

    Returns:
        EdgarCompanyData with revenue if available, else None.
    """
    padded_cik = cik.zfill(10)
    url = EDGAR_COMPANY_FACTS.format(cik=padded_cik)

    try:
        resp = httpx.get(url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        company_name = data.get("entityName", "Unknown")

        # Look for revenue in US-GAAP facts
        us_gaap = data.get("facts", {}).get("us-gaap", {})

        # Try common revenue field names
        revenue_fields = [
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
        ]

        for field_name in revenue_fields:
            if field_name in us_gaap:
                units = us_gaap[field_name].get("units", {}).get("USD", [])
                if units:
                    # Get most recent annual figure
                    annual = [u for u in units if u.get("form") == "10-K"]
                    if annual:
                        latest = sorted(annual, key=lambda x: x.get("end", ""), reverse=True)[0]
                        return EdgarCompanyData(
                            cik=cik,
                            company_name=company_name,
                            revenue=latest.get("val"),
                            revenue_year=int(latest.get("end", "0000")[:4]) if latest.get("end") else None,
                            filing_type="10-K",
                        )

        return EdgarCompanyData(cik=cik, company_name=company_name)

    except httpx.HTTPError as exc:
        logger.error("EDGAR company facts failed for CIK %s: %s", cik, exc)
        return None


def estimate_tam_from_comparables(companies: list[EdgarCompanyData]) -> dict:
    """Estimate TAM from public company revenue data.

    Uses a bottom-up approach: sum comparable revenues and apply a multiplier
    based on the number of comparable companies found.

    Returns:
        Dict with tam_estimate, confidence, and supporting data.
    """
    revenues = [c.revenue for c in companies if c.revenue and c.revenue > 0]

    if not revenues:
        return {
            "tam_estimate": None,
            "tam_confidence": "low",
            "comparable_count": 0,
            "note": "No revenue data found from public comparables",
        }

    total_revenue = sum(revenues)

    if len(revenues) >= 3:
        confidence = "high"
        multiplier = 3.0  # Assume public comps represent ~1/3 of addressable market
    elif len(revenues) >= 2:
        confidence = "medium"
        multiplier = 5.0
    else:
        confidence = "low"
        multiplier = 10.0

    tam_estimate = total_revenue * multiplier

    return {
        "tam_estimate": tam_estimate,
        "tam_confidence": confidence,
        "comparable_count": len(revenues),
        "total_comparable_revenue": total_revenue,
        "comparables": [
            {"name": c.company_name, "revenue": c.revenue, "year": c.revenue_year}
            for c in companies
            if c.revenue
        ],
    }
