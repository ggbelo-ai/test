"""arXiv API integration — fetch recent papers by category and track citation velocity."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import arxiv

logger = logging.getLogger(__name__)

# Categories relevant to venture-scale technology themes
DEFAULT_CATEGORIES = ["cs.AI", "cs.RO", "q-bio", "eess", "cs.LG", "cs.CL"]

ARXIV_MAX_RESULTS = 200


@dataclass
class ArxivSignal:
    """A signal derived from an arXiv paper."""

    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    published: datetime
    pdf_url: str
    source: str = "arxiv"
    citation_velocity: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        return f"arxiv:{self.paper_id}"

    @property
    def text_for_embedding(self) -> str:
        return f"{self.title}. {self.summary}"


def fetch_arxiv_papers(
    last_days: int = 1,
    categories: list[str] | None = None,
    max_results: int = ARXIV_MAX_RESULTS,
) -> list[ArxivSignal]:
    """Fetch recent arXiv papers from specified categories.

    Args:
        last_days: Number of days to look back.
        categories: arXiv category codes to search. Defaults to AI/robotics/bio/EE.
        max_results: Maximum papers to return.

    Returns:
        List of ArxivSignal objects.
    """
    cats = categories or DEFAULT_CATEGORIES
    cutoff = datetime.now(timezone.utc) - timedelta(days=last_days)

    # Build category query: cat:cs.AI OR cat:cs.RO OR ...
    cat_query = " OR ".join(f"cat:{c}" for c in cats)

    search = arxiv.Search(
        query=cat_query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    signals: list[ArxivSignal] = []
    client = arxiv.Client()

    for paper in client.results(search):
        pub_date = paper.published.replace(tzinfo=timezone.utc)
        if pub_date < cutoff:
            break

        signals.append(
            ArxivSignal(
                paper_id=paper.get_short_id(),
                title=paper.title,
                summary=paper.summary,
                authors=[a.name for a in paper.authors],
                categories=paper.categories,
                published=pub_date,
                pdf_url=paper.pdf_url,
                metadata={"primary_category": paper.primary_category},
            )
        )

    logger.info("Fetched %d arXiv papers (last %d days)", len(signals), last_days)
    return signals
