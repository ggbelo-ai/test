"""Y Combinator company list scraper — uses Playwright to extract company data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

YC_COMPANIES_URL = "https://www.ycombinator.com/companies"


@dataclass
class YCCompany:
    """A company from the YC directory."""

    name: str
    description: str
    batch: str
    url: str | None = None
    status: str = ""  # Active, Acquired, Inactive, Public
    industry: str = ""
    location: str = ""
    team_size: str = ""
    metadata: dict = field(default_factory=dict)


async def scrape_yc_companies(
    keywords: str | None = None,
    batch: str | None = None,
    max_results: int = 50,
) -> list[YCCompany]:
    """Scrape the YC company directory filtered by keywords and/or batch.

    Args:
        keywords: Search terms to filter companies (e.g. 'AI infrastructure').
        batch: YC batch filter (e.g. 'W24', 'S23').
        max_results: Maximum companies to return.

    Returns:
        List of YCCompany objects.
    """
    companies: list[YCCompany] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Build URL with query parameters
        url = YC_COMPANIES_URL
        params = []
        if keywords:
            params.append(f"q={keywords}")
        if batch:
            params.append(f"batch={batch}")
        if params:
            url += "?" + "&".join(params)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for company cards to load
            await page.wait_for_selector("a[class*='Company']", timeout=10000)

            # Extract company data from the directory listing
            company_elements = await page.query_selector_all("a[class*='Company']")

            for element in company_elements[:max_results]:
                try:
                    name_el = await element.query_selector("span[class*='coName']")
                    desc_el = await element.query_selector("span[class*='coDescription']")
                    batch_el = await element.query_selector("span[class*='batch']")
                    location_el = await element.query_selector("span[class*='coLocation']")

                    name = await name_el.inner_text() if name_el else ""
                    description = await desc_el.inner_text() if desc_el else ""
                    batch_str = await batch_el.inner_text() if batch_el else ""
                    location = await location_el.inner_text() if location_el else ""

                    href = await element.get_attribute("href")
                    company_url = f"https://www.ycombinator.com{href}" if href else None

                    if name:
                        companies.append(
                            YCCompany(
                                name=name.strip(),
                                description=description.strip(),
                                batch=batch_str.strip(),
                                url=company_url,
                                location=location.strip(),
                            )
                        )
                except Exception as exc:
                    logger.debug("Failed to parse YC company element: %s", exc)

        except Exception as exc:
            logger.error("YC scraper failed: %s", exc)
        finally:
            await browser.close()

    logger.info("Scraped %d YC companies (keywords=%s, batch=%s)", len(companies), keywords, batch)
    return companies
