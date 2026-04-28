"""eBay scraper using the public RSS search feed.

The RSS endpoint requires no auth and returns up to ~50 listings per query.
eBay deprecated the Finding API; the Browse API requires OAuth, so RSS is
the simplest viable path. Note: eBay blocks bot-like IPs at the HTTP layer
on `www.ebay.com` — this scraper is expected to run from a residential IP.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

SOURCE = "ebay"
RSS_URL = "https://www.ebay.com/sch/i.html?_nkw={query}&_rss=1&_sop=10&_ipg=50"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_ID_RE = re.compile(r"/itm/(?:[^/]+/)?(\d{6,})")
_PRICE_RE = re.compile(r"(?:US\s*)?\$\s*([\d,]+(?:\.\d{1,2})?)", re.I)
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


@dataclass
class Listing:
    source: str
    listing_id: str
    title: str
    url: str
    price_usd: float | None
    price_raw: str
    image_url: str | None
    keyword: str

    def title_for_alert(self) -> str:
        return self.title


def _extract_listing_id(url: str) -> str | None:
    m = _ID_RE.search(url or "")
    return m.group(1) if m else None


def _extract_price(text: str) -> tuple[float | None, str]:
    if not text:
        return None, ""
    m = _PRICE_RE.search(text)
    if not m:
        return None, ""
    raw = m.group(0).strip()
    try:
        return float(m.group(1).replace(",", "")), raw
    except ValueError:
        return None, raw


def _extract_image(html: str) -> str | None:
    if not html:
        return None
    m = _IMG_RE.search(html)
    return m.group(1) if m else None


def parse_rss(content: bytes, keyword: str) -> List[Listing]:
    """Parse eBay RSS XML bytes into Listing objects. Pure function — no network."""
    root = ET.fromstring(content)
    listings: List[Listing] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""
        listing_id = _extract_listing_id(link)
        if not listing_id or not title:
            continue
        price_usd, price_raw = _extract_price(description)
        if price_usd is None:
            price_usd, price_raw = _extract_price(title)
        listings.append(
            Listing(
                source=SOURCE,
                listing_id=listing_id,
                title=title,
                url=link,
                price_usd=price_usd,
                price_raw=price_raw,
                image_url=_extract_image(description),
                keyword=keyword,
            )
        )
    return listings


def search(keyword: str, timeout: int = 20) -> List[Listing]:
    """Live RSS query for one keyword. Returns [] on network or parse error.

    The keyword is wrapped in double-quotes before URL-encoding so eBay
    treats it as an exact phrase. Without this, eBay's spell-corrector
    silently rewrites unfamiliar brands (e.g. "Autmog" -> "Automag",
    paintball gear) and the watcher would never see the right listings.
    """
    quoted = keyword if keyword.startswith('"') and keyword.endswith('"') else f'"{keyword}"'
    url = RSS_URL.format(query=quote_plus(quoted))
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        if "xml" not in resp.headers.get("content-type", "").lower() and not resp.content.lstrip().startswith(b"<?xml"):
            logger.warning("eBay returned non-XML for %r (status %s) — likely bot-blocked", keyword, resp.status_code)
            return []
        return parse_rss(resp.content, keyword)
    except requests.RequestException as e:
        logger.warning("eBay RSS fetch failed for %r: %s", keyword, e)
        return []
    except ET.ParseError as e:
        logger.warning("eBay RSS parse failed for %r: %s", keyword, e)
        return []
