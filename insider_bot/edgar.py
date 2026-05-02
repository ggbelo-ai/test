"""SEC EDGAR fetcher and Form 4 parser.

Uses three free public endpoints:

  - https://www.sec.gov/files/company_tickers.json
  - https://data.sec.gov/submissions/CIK{cik}.json
  - https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary}

SEC fair-use policy: descriptive User-Agent, ~10 requests/second.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import requests
from lxml import etree

from . import config

log = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}"

REQUEST_INTERVAL = 0.12  # ~8 req/s, comfortably under SEC's 10 req/s


@dataclass
class InsiderTxn:
    accession: str
    ticker: str
    cik: str
    owner_cik: str | None
    owner_name: str
    owner_title: str | None
    is_director: bool
    is_officer: bool
    is_ten_percent: bool
    transaction_date: str  # YYYY-MM-DD
    filing_date: str
    code: str
    shares: float
    price: float
    value: float


class EdgarClient:
    def __init__(self, user_agent: str | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent or config.SEC_USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request = 0.0

    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_request
        if delta < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - delta)
        self._last_request = time.monotonic()

    def _get(self, url: str, *, retries: int = 3) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (429, 502, 503, 504):
                    backoff = 2 ** attempt
                    log.warning("SEC %s on %s; backing off %ss", resp.status_code, url, backoff)
                    time.sleep(backoff)
                    continue
                resp.raise_for_status()
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to fetch {url}")

    # -- ticker / CIK mapping -------------------------------------------------

    def load_ticker_map(self) -> dict[str, str]:
        """Return {ticker_upper: cik_int_str} for all SEC-known tickers."""
        cache = config.CACHE_DIR / "company_tickers.json"
        config.ensure_dirs()
        if cache.exists() and _age_hours(cache) < 24:
            data = json.loads(cache.read_text())
        else:
            resp = self._get(TICKER_MAP_URL)
            data = resp.json()
            cache.write_text(resp.text)
        return {row["ticker"].upper(): str(row["cik_str"]) for row in data.values()}

    def cik_for(self, ticker: str) -> str | None:
        return self.load_ticker_map().get(ticker.upper())

    # -- submissions ----------------------------------------------------------

    def list_form4_filings(
        self, cik: str, *, since: date | None = None
    ) -> list[dict]:
        """Return [{accession, filing_date, primary_doc, form}] for Form 4 filings."""
        cik10 = str(cik).zfill(10)
        resp = self._get(SUBMISSIONS_URL.format(cik10=cik10))
        body = resp.json()
        recent = body.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        out: list[dict] = []
        for form, acc, fdate, doc in zip(forms, accessions, filing_dates, primary_docs):
            if form != "4":
                continue
            if since and fdate < since.isoformat():
                continue
            out.append(
                {
                    "accession": acc,
                    "filing_date": fdate,
                    "primary_doc": doc,
                    "form": form,
                }
            )
        return out

    # -- Form 4 XML -----------------------------------------------------------

    def fetch_form4_xml(self, cik: str, accession: str) -> bytes | None:
        """Return primary Form 4 XML bytes or None if unavailable."""
        acc_nodash = accession.replace("-", "")
        base = ARCHIVE_BASE.format(cik=int(cik), acc_nodash=acc_nodash)
        idx_url = f"{base}/index.json"
        try:
            idx = self._get(idx_url).json()
        except Exception as exc:
            log.warning("index.json failed for %s/%s: %s", cik, accession, exc)
            return None
        items = idx.get("directory", {}).get("item", [])
        # Find an XML doc that isn't the filing's own *-index.xml.
        candidates = [
            it["name"]
            for it in items
            if it.get("name", "").lower().endswith(".xml")
            and not it["name"].lower().endswith("-index.xml")
        ]
        if not candidates:
            return None
        # Prefer ones that look like Form 4.
        candidates.sort(key=lambda n: 0 if "form4" in n.lower() or n.lower().startswith("wf-form4") else 1)
        try:
            return self._get(f"{base}/{candidates[0]}").content
        except Exception as exc:
            log.warning("xml fetch failed for %s/%s: %s", cik, accession, exc)
            return None


def _age_hours(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 3600.0


# -- Parsing -----------------------------------------------------------------

def _text(node, xpath: str) -> str | None:
    found = node.find(xpath)
    if found is None:
        return None
    txt = found.text
    return txt.strip() if txt else None


def _flag(node, xpath: str) -> bool:
    val = _text(node, xpath)
    if val is None:
        return False
    return val.strip() in ("1", "true", "True")


def parse_form4(
    xml_bytes: bytes,
    *,
    accession: str,
    ticker: str,
    cik: str,
    filing_date: str,
) -> list[InsiderTxn]:
    """Parse a Form 4 XML and return non-derivative purchase transactions only."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        log.warning("XML parse error for %s: %s", accession, exc)
        return []

    owner = root.find(".//reportingOwner")
    if owner is None:
        return []
    owner_cik = _text(owner, "reportingOwnerId/rptOwnerCik")
    owner_name = _text(owner, "reportingOwnerId/rptOwnerName") or "UNKNOWN"
    rel = owner.find("reportingOwnerRelationship")
    is_director = _flag(rel, "isDirector") if rel is not None else False
    is_officer = _flag(rel, "isOfficer") if rel is not None else False
    is_ten_percent = _flag(rel, "isTenPercentOwner") if rel is not None else False
    owner_title = (_text(rel, "officerTitle") if rel is not None else None) or None

    txns: list[InsiderTxn] = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = _text(tx, "transactionCoding/transactionCode") or ""
        if not code.startswith("P"):
            continue
        tdate = _text(tx, "transactionDate/value")
        shares = _text(tx, "transactionAmounts/transactionShares/value")
        price = _text(tx, "transactionAmounts/transactionPricePerShare/value")
        if not (tdate and shares and price):
            continue
        try:
            shares_f = float(shares)
            price_f = float(price)
        except ValueError:
            continue
        if shares_f <= 0 or price_f <= 0:
            continue
        value = shares_f * price_f
        txns.append(
            InsiderTxn(
                accession=accession,
                ticker=ticker,
                cik=str(cik),
                owner_cik=owner_cik,
                owner_name=owner_name,
                owner_title=owner_title,
                is_director=is_director,
                is_officer=is_officer,
                is_ten_percent=is_ten_percent,
                transaction_date=tdate,
                filing_date=filing_date,
                code=code,
                shares=shares_f,
                price=price_f,
                value=value,
            )
        )
    return txns


# -- High-level refresh ------------------------------------------------------

def refresh_universe_transactions(
    universe: Iterable[str] | None = None,
    *,
    since: date | None = None,
) -> list[InsiderTxn]:
    """Fetch + parse Form 4 purchase txns for the universe; return collected list."""
    client = EdgarClient()
    universe = list(universe) if universe else list(config.UNIVERSE.keys())
    out: list[InsiderTxn] = []
    seen_ciks: set[str] = set()  # multiple tickers can share one issuer CIK (e.g. GOOGL/GOOG)
    for ticker in universe:
        cik = client.cik_for(ticker)
        if not cik:
            log.info("no CIK for %s", ticker)
            continue
        if cik in seen_ciks:
            log.info("skipping %s: CIK %s already fetched", ticker, cik)
            continue
        seen_ciks.add(cik)
        try:
            filings = client.list_form4_filings(cik, since=since)
        except Exception as exc:
            log.warning("filings fetch failed for %s: %s", ticker, exc)
            continue
        for f in filings:
            xml = client.fetch_form4_xml(cik, f["accession"])
            if not xml:
                continue
            out.extend(
                parse_form4(
                    xml,
                    accession=f["accession"],
                    ticker=ticker,
                    cik=cik,
                    filing_date=f["filing_date"],
                )
            )
    return out
