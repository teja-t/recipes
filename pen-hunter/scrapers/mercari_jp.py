"""Mercari JP scraper via the public web API.

Mercari's web client uses DPoP-signed requests (RFC 9449). Each request
carries a `DPoP` header containing a fresh ECDSA P-256 JWT that proves
possession of a keypair. No user login is needed for search — the keypair
is generated per process and used to sign every search call.

The endpoint POST https://api.mercari.jp/v2/entities:search returns JSON
with item objects. Titles come back in Japanese and are translated to
English by translate.py before alerts are sent.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import List

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)

SOURCE = "mercari_jp"
SEARCH_URL = "https://api.mercari.jp/v2/entities:search"
ITEM_URL = "https://jp.mercari.com/item/{id}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Lazy-initialized ECDSA keypair, reused for every DPoP token in this process.
_key: ec.EllipticCurvePrivateKey | None = None
_jwk: dict | None = None
_key_lock = Lock()

# Naive USD/JPY rate cache. Refreshed on first use; falls back to a hardcoded
# rate if the FX endpoint is unreachable. Bunjang will share the same pattern
# via its own KRW pair when we get to Step 6.
_FX_FALLBACK_USD_PER_JPY = 1.0 / 150.0
_fx_cache: dict[str, tuple[float, float]] = {}  # symbol -> (rate, fetched_at)
_FX_TTL_SECONDS = 60 * 60 * 12


@dataclass
class Listing:
    source: str
    listing_id: str
    title: str
    title_en: str | None
    description_en: str | None
    url: str
    price_jpy: int
    price_usd: float | None
    price_raw: str
    image_url: str | None
    keyword: str

    def title_for_alert(self) -> str:
        return self.title_en or self.title


def _ensure_keypair() -> tuple[ec.EllipticCurvePrivateKey, dict]:
    global _key, _jwk
    with _key_lock:
        if _key is None:
            _key = ec.generate_private_key(ec.SECP256R1())
            nums = _key.public_key().public_numbers()
            b64u = lambda n: base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()
            _jwk = {"kty": "EC", "crv": "P-256", "x": b64u(nums.x), "y": b64u(nums.y)}
        return _key, _jwk


def _dpop(method: str, url: str) -> str:
    key, jwk_pub = _ensure_keypair()
    return jwt.encode(
        {"iat": int(time.time()), "jti": str(uuid.uuid4()), "htu": url, "htm": method},
        key,
        algorithm="ES256",
        headers={"typ": "dpop+jwt", "jwk": jwk_pub},
    )


def _usd_per_jpy(timeout: int = 5) -> float:
    cached = _fx_cache.get("JPY")
    if cached and (time.time() - cached[1]) < _FX_TTL_SECONDS:
        return cached[0]
    try:
        r = requests.get("https://open.er-api.com/v6/latest/JPY", timeout=timeout)
        r.raise_for_status()
        rate = float(r.json()["rates"]["USD"])
        _fx_cache["JPY"] = (rate, time.time())
        return rate
    except (requests.RequestException, KeyError, ValueError) as e:
        logger.warning("USD/JPY FX fetch failed (%s) — using fallback ~150 JPY/USD", e)
        return _FX_FALLBACK_USD_PER_JPY


def _build_search_body(keyword: str, page_size: int) -> dict:
    return {
        "userId": "",
        "pageSize": page_size,
        "pageToken": "",
        "searchSessionId": str(uuid.uuid4()),
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": {
            "keyword": keyword,
            "excludeKeyword": "",
            "sort": "SORT_CREATED_TIME",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
            "sizeId": [],
            "categoryId": [],
            "brandId": [],
            "sellerId": [],
            "priceMin": 0,
            "priceMax": 0,
            "itemConditionId": [],
            "shippingPayerId": [],
            "shippingFromArea": [],
            "shippingMethod": [],
            "colorId": [],
            "hasCoupon": False,
            "attributes": [],
            "itemTypes": [],
            "skuIds": [],
        },
        "defaultDatasets": ["DATASET_TYPE_MERCARI", "DATASET_TYPE_BEYOND"],
        "serviceFrom": "suruga",
        "withItemBrand": True,
        "withItemSize": False,
        "withItemPromotions": True,
        "withItemSizes": True,
        "withShopname": False,
    }


def _to_listing(item: dict, keyword: str, usd_per_jpy: float) -> Listing | None:
    listing_id = item.get("id") or ""
    name = (item.get("name") or "").strip()
    if not listing_id or not name:
        return None
    try:
        price_jpy = int(item.get("price") or 0)
    except (TypeError, ValueError):
        price_jpy = 0
    thumbnails = item.get("thumbnails") or []
    image_url = thumbnails[0] if thumbnails else None
    price_usd = round(price_jpy * usd_per_jpy, 2) if price_jpy > 0 else None
    return Listing(
        source=SOURCE,
        listing_id=listing_id,
        title=name,
        title_en=None,
        description_en=None,
        url=ITEM_URL.format(id=listing_id),
        price_jpy=price_jpy,
        price_usd=price_usd,
        price_raw=f"¥{price_jpy:,}",
        image_url=image_url,
        keyword=keyword,
    )


def search(keyword: str, page_size: int = 30, timeout: int = 20) -> List[Listing]:
    """Live DPoP-signed search. Returns [] on network/parse failure."""
    body = _build_search_body(keyword, page_size)
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
        "X-Platform": "web",
        "DPoP": _dpop("POST", SEARCH_URL),
    }
    try:
        resp = requests.post(SEARCH_URL, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Mercari search failed for %r: %s", keyword, e)
        return []
    items = data.get("items") or []
    rate = _usd_per_jpy()
    out: List[Listing] = []
    for it in items:
        L = _to_listing(it, keyword, rate)
        if L is not None:
            out.append(L)
    return out
