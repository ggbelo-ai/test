"""LinkedIn public profile scraper — Playwright-based, public pages only.

WARNING: LinkedIn aggressively blocks scrapers. This module is designed for
cautious, low-volume scraping of public profile pages only. No authenticated
scraping is performed. Use responsibly and respect rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


@dataclass
class LinkedInProfile:
    """Parsed data from a public LinkedIn profile."""

    name: str
    headline: str = ""
    location: str = ""
    current_company: str = ""
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    profile_url: str = ""
    metadata: dict = field(default_factory=dict)


async def scrape_linkedin_profile(profile_url: str) -> LinkedInProfile | None:
    """Scrape a public LinkedIn profile page.

    Args:
        profile_url: Full LinkedIn profile URL (e.g. https://linkedin.com/in/username).

    Returns:
        LinkedInProfile if successful, None if blocked or not found.
    """
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
            # Random delay to reduce detection
            await asyncio.sleep(random.uniform(2, 5))

            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)

            # Check if we hit an auth wall
            if "authwall" in page.url or "login" in page.url:
                logger.warning("LinkedIn auth wall hit for %s", profile_url)
                return None

            # Wait for basic profile content
            await page.wait_for_selector("h1", timeout=10000)

            name = ""
            headline = ""
            location = ""

            name_el = await page.query_selector("h1")
            if name_el:
                name = (await name_el.inner_text()).strip()

            headline_el = await page.query_selector("div.text-body-medium")
            if headline_el:
                headline = (await headline_el.inner_text()).strip()

            location_el = await page.query_selector("span.text-body-small[class*='location']")
            if location_el:
                location = (await location_el.inner_text()).strip()

            if not name:
                logger.warning("Could not extract profile name from %s", profile_url)
                return None

            return LinkedInProfile(
                name=name,
                headline=headline,
                location=location,
                profile_url=profile_url,
            )

        except Exception as exc:
            logger.error("LinkedIn scraper failed for %s: %s", profile_url, exc)
            return None
        finally:
            await browser.close()
