"""Bunjang scraper via the public unofficial REST API.

`api.bunjang.co.kr/api/1/find_v2.json` returns search results as JSON
with no auth required. Status codes:
    "0" -> for sale
    "1" -> reserved (still browsable)
    "2" -> sold
We surface only status "0" and "1" so reserved items still trigger an
alert (a buyer pulled out + the listing is still live).

Image URLs come back with a literal `{res}` placeholder; we substitute
600 for a clean Telegram preview.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus

import requests

import fx

logger = logging.getLogger(__name__)

SOURCE = "bunjang"
SEARCH_URL = "https://api.bunjang.co.kr/api/1/find_v2.json?q={q}&order=date&page=0&n={n}"
ITEM_URL = "https://m.bunjang.co.kr/products/{pid}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_LIVE_STATUSES = {"0", "1"}


@dataclass
class Listing:
    source: str
    listing_id: str
    title: str
    title_en: str | None
    description_en: str | None
    url: str
    price_krw: int
    price_usd: float | None
    price_raw: str
    image_url: str | None
    keyword: str

    def title_for_alert(self) -> str:
        return self.title_en or self.title


def _resolve_image(template: str, res: int = 600) -> str | None:
    if not template:
        return None
    return template.replace("{res}", str(res))


def _to_listing(item: dict, keyword: str, usd_per_krw: float) -> Listing | None:
    pid = str(item.get("pid") or "").strip()
    name = (item.get("name") or "").strip()
    status = str(item.get("status") or "")
    if not pid or not name or status not in _LIVE_STATUSES:
        return None
    try:
        price_krw = int(item.get("price") or 0)
    except (TypeError, ValueError):
        price_krw = 0
    price_usd = round(price_krw * usd_per_krw, 2) if price_krw > 0 else None
    return Listing(
        source=SOURCE,
        listing_id=pid,
        title=name,
        title_en=None,
        description_en=None,
        url=ITEM_URL.format(pid=pid),
        price_krw=price_krw,
        price_usd=price_usd,
        price_raw=f"₩{price_krw:,}",
        image_url=_resolve_image(item.get("product_image") or ""),
        keyword=keyword,
    )


def search(keyword: str, n: int = 30, timeout: int = 20) -> List[Listing]:
    """Live search for one keyword. Returns [] on failure."""
    url = SEARCH_URL.format(q=quote_plus(keyword), n=n)
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Bunjang search failed for %r: %s", keyword, e)
        return []
    if data.get("result") != "success":
        logger.warning("Bunjang non-success response for %r: %s", keyword, data.get("result"))
        return []
    items = data.get("list") or []
    rate = fx.usd_per_krw()
    out: List[Listing] = []
    for it in items:
        if it.get("ad"):
            continue  # skip promoted listings
        L = _to_listing(it, keyword, rate)
        if L is not None:
            out.append(L)
    return out
