"""USPTO Patent API integration — fetch recent patent filings by technology classification."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

# USPTO PatentsView API base URL
PATENTSVIEW_API = "https://api.patentsview.org/patents/query"

# CPC classification codes relevant to emerging tech
DEFAULT_CPC_CODES = [
    "G06N",  # Computing arrangements based on specific computational models (AI/ML)
    "G06F40",  # Natural language processing
    "B25J",  # Robotics
    "H04L",  # Digital information transmission (networking, security)
    "G16H",  # Healthcare informatics
    "G16B",  # Bioinformatics
]


@dataclass
class PatentSignal:
    """A signal derived from a USPTO patent filing."""

    patent_id: str
    title: str
    abstract: str
    assignee: str | None
    filing_date: str
    cpc_codes: list[str]
    inventors: list[str]
    source: str = "uspto"
    metadata: dict = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        return f"uspto:{self.patent_id}"

    @property
    def text_for_embedding(self) -> str:
        return f"{self.title}. {self.abstract}"


def fetch_patent_filings(
    last_days: int = 7,
    cpc_codes: list[str] | None = None,
    max_results: int = 100,
) -> list[PatentSignal]:
    """Fetch recent patent filings from USPTO PatentsView API.

    Args:
        last_days: Number of days to look back.
        cpc_codes: CPC classification codes to filter by.
        max_results: Maximum number of patents to return.

    Returns:
        List of PatentSignal objects.
    """
    codes = cpc_codes or DEFAULT_CPC_CODES
    cutoff = (datetime.now(timezone.utc) - timedelta(days=last_days)).strftime("%Y-%m-%d")

    # Build CPC subgroup filter
    cpc_filters = [{"cpc_subgroup_id": code} for code in codes]

    query_params = {
        "q": {
            "_and": [
                {"_gte": {"app_date": cutoff}},
                {"_or": cpc_filters},
            ]
        },
        "f": [
            "patent_id", "patent_title", "patent_abstract",
            "assignee_organization", "app_date",
            "inventor_first_name", "inventor_last_name",
            "cpc_subgroup_id",
        ],
        "o": {"per_page": max_results},
    }

    signals: list[PatentSignal] = []

    try:
        response = httpx.post(PATENTSVIEW_API, json=query_params, timeout=30)
        response.raise_for_status()
        data = response.json()

        patents = data.get("patents", [])
        for patent in patents:
            inventors = []
            for inv in patent.get("inventors", []):
                name = f"{inv.get('inventor_first_name', '')} {inv.get('inventor_last_name', '')}".strip()
                if name:
                    inventors.append(name)

            cpc_list = [
                c.get("cpc_subgroup_id", "")
                for c in patent.get("cpcs", [])
                if c.get("cpc_subgroup_id")
            ]

            assignees = patent.get("assignees", [])
            assignee = assignees[0].get("assignee_organization") if assignees else None

            signals.append(
                PatentSignal(
                    patent_id=patent.get("patent_id", ""),
                    title=patent.get("patent_title", ""),
                    abstract=patent.get("patent_abstract", ""),
                    assignee=assignee,
                    filing_date=patent.get("app_date", ""),
                    cpc_codes=cpc_list,
                    inventors=inventors,
                )
            )
    except httpx.HTTPError as exc:
        logger.error("USPTO API request failed: %s", exc)

    logger.info("Fetched %d patent filings (last %d days)", len(signals), last_days)
    return signals
