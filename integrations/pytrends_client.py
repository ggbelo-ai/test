"""Google Trends integration via pytrends — keyword acceleration curves."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pytrends.request import TrendReq

logger = logging.getLogger(__name__)


@dataclass
class TrendsSignal:
    """A signal derived from Google Trends keyword acceleration."""

    keyword: str
    interest_over_time: list[dict]  # [{date, value}, ...]
    acceleration: float  # positive = accelerating interest
    related_queries: list[str]
    source: str = "pytrends"
    metadata: dict = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        return f"pytrends:{self.keyword}"

    @property
    def text_for_embedding(self) -> str:
        related = ", ".join(self.related_queries[:10]) if self.related_queries else ""
        return f"Google Trends keyword: {self.keyword}. Related: {related}"


def fetch_pytrends_acceleration(
    keywords: list[str],
    timeframe: str = "today 3-m",
    geo: str = "",
) -> list[TrendsSignal]:
    """Fetch Google Trends data and compute acceleration for given keywords.

    Acceleration is measured as the slope of the last 4 weeks' interest
    relative to the prior 4 weeks. Positive values indicate growing interest.

    Args:
        keywords: List of keywords to track (max 5 per batch due to API limits).
        timeframe: Pytrends timeframe string.
        geo: Geographic filter (empty = worldwide).

    Returns:
        List of TrendsSignal objects.
    """
    signals: list[TrendsSignal] = []
    pytrends = TrendReq(hl="en-US")

    # Process in batches of 5 (pytrends limit)
    for i in range(0, len(keywords), 5):
        batch = keywords[i : i + 5]

        try:
            pytrends.build_payload(batch, timeframe=timeframe, geo=geo)

            # Interest over time
            interest_df = pytrends.interest_over_time()
            if interest_df.empty:
                continue

            for kw in batch:
                if kw not in interest_df.columns:
                    continue

                series = interest_df[kw]
                values = [
                    {"date": idx.isoformat(), "value": int(val)}
                    for idx, val in series.items()
                ]

                # Compute acceleration: compare recent vs earlier period
                if len(series) >= 8:
                    recent = series[-4:].mean()
                    earlier = series[-8:-4].mean()
                    acceleration = (recent - earlier) / max(earlier, 1)
                else:
                    acceleration = 0.0

                # Fetch related queries
                related = []
                try:
                    related_df = pytrends.related_queries()
                    if kw in related_df and related_df[kw].get("rising") is not None:
                        related = related_df[kw]["rising"]["query"].tolist()[:10]
                except Exception:
                    pass

                signals.append(
                    TrendsSignal(
                        keyword=kw,
                        interest_over_time=values,
                        acceleration=round(acceleration, 3),
                        related_queries=related,
                    )
                )

        except Exception as exc:
            logger.warning("pytrends batch failed for %s: %s", batch, exc)

    logger.info("Fetched trends data for %d keywords", len(signals))
    return signals
