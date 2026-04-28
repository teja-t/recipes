"""Foreign-exchange rate cache for converting marketplace prices to USD.

Lookups are cached in-process for FX_TTL_SECONDS so polling doesn't spam
the FX endpoint. open.er-api.com is free and unauthenticated; if it
becomes unreachable, hardcoded fallbacks keep alerts flowing rather
than failing closed.
"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

FX_TTL_SECONDS = 60 * 60 * 12

# Approximate fallbacks (2026 ballpark). Refreshed live whenever possible.
_FALLBACK_USD_PER = {
    "JPY": 1.0 / 150.0,
    "KRW": 1.0 / 1380.0,
}

_cache: dict[str, tuple[float, float]] = {}


def usd_per(currency: str, timeout: int = 5) -> float:
    """USD per 1 unit of `currency` (e.g. 0.0067 for JPY)."""
    currency = currency.upper()
    cached = _cache.get(currency)
    if cached and (time.time() - cached[1]) < FX_TTL_SECONDS:
        return cached[0]
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{currency}", timeout=timeout)
        r.raise_for_status()
        rate = float(r.json()["rates"]["USD"])
        _cache[currency] = (rate, time.time())
        return rate
    except (requests.RequestException, KeyError, ValueError) as e:
        fallback = _FALLBACK_USD_PER.get(currency)
        if fallback is None:
            raise
        logger.warning("FX %s->USD fetch failed (%s) — using fallback", currency, e)
        return fallback


def usd_per_jpy(timeout: int = 5) -> float:
    return usd_per("JPY", timeout)


def usd_per_krw(timeout: int = 5) -> float:
    return usd_per("KRW", timeout)
