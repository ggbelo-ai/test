"""Semantic Scholar API integration — track researchers and detect career transitions.

Uses the free Semantic Scholar Academic Graph API (no key required, rate-limited).
Detects researchers leaving academia who may be founding companies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"

# Fields to request for author searches
AUTHOR_FIELDS = "name,url,paperCount,citationCount,hIndex,affiliations,homepage,externalIds"
PAPER_FIELDS = "title,abstract,year,citationCount,fieldsOfStudy,publicationTypes,externalIds,authors"


@dataclass
class Researcher:
    """A researcher profile from Semantic Scholar."""

    author_id: str
    name: str
    paper_count: int = 0
    citation_count: int = 0
    h_index: int = 0
    affiliations: list[str] = field(default_factory=list)
    homepage: str = ""
    recent_papers: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ResearcherSignal:
    """A signal indicating a researcher may be transitioning to industry/founding."""

    author_id: str
    name: str
    signal_type: str  # 'affiliation_change', 'publication_gap', 'industry_pivot'
    description: str
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        return f"semantic_scholar:{self.author_id}"


def search_authors(query: str, limit: int = 10) -> list[Researcher]:
    """Search for researchers by name or topic.

    Args:
        query: Search query (name or research topic).
        limit: Maximum results.

    Returns:
        List of Researcher objects.
    """
    url = f"{S2_API_BASE}/author/search"
    params = {"query": query, "limit": limit, "fields": AUTHOR_FIELDS}
    researchers: list[Researcher] = []

    try:
        resp = httpx.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("data", []):
            researchers.append(
                Researcher(
                    author_id=item["authorId"],
                    name=item.get("name", ""),
                    paper_count=item.get("paperCount", 0),
                    citation_count=item.get("citationCount", 0),
                    h_index=item.get("hIndex", 0),
                    affiliations=item.get("affiliations", []),
                    homepage=item.get("homepage", ""),
                )
            )
    except httpx.HTTPError as exc:
        logger.error("Semantic Scholar author search failed: %s", exc)

    return researchers


def get_author_papers(
    author_id: str,
    limit: int = 20,
    year_min: int | None = None,
) -> list[dict]:
    """Fetch recent papers by an author.

    Args:
        author_id: Semantic Scholar author ID.
        limit: Maximum papers to return.
        year_min: Only return papers from this year onwards.

    Returns:
        List of paper dicts.
    """
    url = f"{S2_API_BASE}/author/{author_id}/papers"
    params = {"limit": limit, "fields": PAPER_FIELDS}
    papers: list[dict] = []

    try:
        resp = httpx.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("data", []):
            year = item.get("year")
            if year_min and year and year < year_min:
                continue
            papers.append({
                "title": item.get("title", ""),
                "abstract": item.get("abstract", ""),
                "year": year,
                "citation_count": item.get("citationCount", 0),
                "fields_of_study": item.get("fieldsOfStudy", []),
                "authors": [a.get("name", "") for a in item.get("authors", [])],
            })
    except httpx.HTTPError as exc:
        logger.error("Semantic Scholar papers fetch failed for %s: %s", author_id, exc)

    return papers


def detect_publication_gap(papers: list[dict], gap_years: int = 2) -> bool:
    """Detect if a researcher has stopped publishing (potential career transition).

    Args:
        papers: List of paper dicts with 'year' field.
        gap_years: Number of years without publication to flag.

    Returns:
        True if a publication gap is detected.
    """
    if not papers:
        return False

    years = sorted([p["year"] for p in papers if p.get("year")], reverse=True)
    if not years:
        return False

    from datetime import datetime
    current_year = datetime.now().year
    most_recent = years[0]

    return (current_year - most_recent) >= gap_years


def detect_industry_pivot(papers: list[dict], min_papers: int = 3) -> bool:
    """Detect if recent papers shift toward applied/industry topics.

    Looks for papers with applied keywords vs pure academic topics.
    """
    if len(papers) < min_papers:
        return False

    industry_keywords = {
        "system", "production", "deployment", "scalable", "real-world",
        "industry", "application", "platform", "framework", "tool",
        "startup", "commercial", "product",
    }

    recent_papers = sorted(papers, key=lambda p: p.get("year", 0), reverse=True)[:5]

    applied_count = 0
    for paper in recent_papers:
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        if any(kw in text for kw in industry_keywords):
            applied_count += 1

    return applied_count >= (len(recent_papers) * 0.6)


def scan_researchers_for_signals(
    author_ids: list[str],
    previous_affiliations: dict[str, list[str]] | None = None,
) -> list[ResearcherSignal]:
    """Scan a list of researchers for transition signals.

    Args:
        author_ids: Semantic Scholar author IDs to check.
        previous_affiliations: Dict of author_id → previous affiliations for change detection.

    Returns:
        List of ResearcherSignals.
    """
    previous = previous_affiliations or {}
    signals: list[ResearcherSignal] = []

    for author_id in author_ids:
        researchers = search_authors(author_id, limit=1)
        if not researchers:
            continue

        researcher = researchers[0]
        papers = get_author_papers(author_id, limit=20, year_min=2023)

        # Check for affiliation change
        prev_affiliations = previous.get(author_id, [])
        if prev_affiliations and researcher.affiliations != prev_affiliations:
            signals.append(
                ResearcherSignal(
                    author_id=author_id,
                    name=researcher.name,
                    signal_type="affiliation_change",
                    description=(
                        f"Affiliation changed from {prev_affiliations} to {researcher.affiliations}"
                    ),
                    confidence=0.7,
                    metadata={
                        "previous": prev_affiliations,
                        "current": researcher.affiliations,
                    },
                )
            )

        # Check for publication gap
        if detect_publication_gap(papers):
            signals.append(
                ResearcherSignal(
                    author_id=author_id,
                    name=researcher.name,
                    signal_type="publication_gap",
                    description="Researcher has not published in 2+ years — possible career transition",
                    confidence=0.5,
                )
            )

        # Check for industry pivot
        if detect_industry_pivot(papers):
            signals.append(
                ResearcherSignal(
                    author_id=author_id,
                    name=researcher.name,
                    signal_type="industry_pivot",
                    description="Recent papers show shift toward applied/industry topics",
                    confidence=0.6,
                    metadata={"recent_paper_count": len(papers)},
                )
            )

    logger.info(
        "Scanned %d researchers, found %d signals", len(author_ids), len(signals)
    )
    return signals
