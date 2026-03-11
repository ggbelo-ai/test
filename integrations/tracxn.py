"""Tracxn free snippets scraper — Playwright-based company data extraction.

Scrapes publicly available company snippets from Tracxn search results.
No authenticated access; only public page data.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

TRACXN_SEARCH_URL = "https://tracxn.com/d/companies"


@dataclass
class TracxnCompany:
    """A company record scraped from Tracxn."""

    name: str
    description: str = ""
    sector: str = ""
    stage: str = ""
    location: str = ""
    founded_year: str = ""
    employee_range: str = ""
    url: str = ""
    tracxn_url: str = ""
    source: str = "tracxn"
    metadata: dict = field(default_factory=dict)


async def scrape_tracxn_companies(
    keywords: str,
    max_results: int = 30,
) -> list[TracxnCompany]:
    """Scrape Tracxn search results for companies matching keywords.

    Uses Playwright to render the JavaScript-heavy Tracxn pages.
    Includes random delays to reduce detection risk.

    Args:
        keywords: Search terms (e.g. 'neuromorphic computing').
        max_results: Maximum companies to extract.

    Returns:
        List of TracxnCompany objects.
    """
    companies: list[TracxnCompany] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            # Random delay before request
            await asyncio.sleep(random.uniform(1, 3))

            search_url = f"{TRACXN_SEARCH_URL}?search={keywords}"
            await page.goto(search_url, wait_until="networkidle", timeout=30000)

            # Wait for company cards to render
            await page.wait_for_selector("[class*='company']", timeout=15000)

            # Extract company data from search result cards
            cards = await page.query_selector_all("[class*='companyCard'], [class*='company-card'], tr[class*='company']")

            for card in cards[:max_results]:
                try:
                    name = ""
                    description = ""
                    sector = ""
                    location = ""

                    name_el = await card.query_selector("[class*='name'], [class*='title'], a h3, a h4")
                    if name_el:
                        name = (await name_el.inner_text()).strip()

                    desc_el = await card.query_selector("[class*='description'], [class*='desc'], p")
                    if desc_el:
                        description = (await desc_el.inner_text()).strip()

                    sector_el = await card.query_selector("[class*='sector'], [class*='industry']")
                    if sector_el:
                        sector = (await sector_el.inner_text()).strip()

                    location_el = await card.query_selector("[class*='location'], [class*='geo']")
                    if location_el:
                        location = (await location_el.inner_text()).strip()

                    link_el = await card.query_selector("a[href*='/d/companies/']")
                    tracxn_url = ""
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            tracxn_url = f"https://tracxn.com{href}" if href.startswith("/") else href

                    if name:
                        companies.append(
                            TracxnCompany(
                                name=name,
                                description=description[:500],
                                sector=sector,
                                location=location,
                                tracxn_url=tracxn_url,
                            )
                        )

                    # Small delay between parsing to be polite
                    await asyncio.sleep(random.uniform(0.1, 0.3))

                except Exception as exc:
                    logger.debug("Failed to parse Tracxn card: %s", exc)

        except Exception as exc:
            logger.error("Tracxn scraper failed for '%s': %s", keywords, exc)
        finally:
            await browser.close()

    logger.info("Scraped %d companies from Tracxn for '%s'", len(companies), keywords)
    return companies
