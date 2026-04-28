"""Telegram notifier.

Sends one alert per new listing. Uses sendPhoto when an image URL is
available (caption holds the message body), otherwise sendMessage. HTML
parse mode lets us bold the title and embed a clickable "View listing"
link without exposing raw URLs.
"""
from __future__ import annotations

import html
import logging

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


def _format_message(listing) -> str:
    title = listing.title_for_alert() if hasattr(listing, "title_for_alert") else listing.title
    price_line = (
        f"${listing.price_usd:,.2f} USD" if getattr(listing, "price_usd", None) is not None
        else (getattr(listing, "price_raw", "") or "price unknown")
    )
    return (
        f"<b>{html.escape(title)}</b>\n"
        f"{price_line}\n"
        f"Source: {html.escape(listing.source)}\n"
        f"Matched: {html.escape(listing.keyword)}\n"
        f'<a href="{html.escape(listing.url, quote=True)}">View listing</a>'
    )


def _post(method: str, payload: dict, timeout: int = 15) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not set in .env (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return False
    url = API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if not r.ok:
            logger.warning("Telegram %s failed: %s %s", method, r.status_code, r.text[:300])
            return False
        return True
    except requests.RequestException as e:
        logger.warning("Telegram %s network error: %s", method, e)
        return False


def send_alert(listing) -> bool:
    """Send a Telegram alert for a single listing. Returns True on success."""
    text = _format_message(listing)
    image = getattr(listing, "image_url", None)
    if image:
        ok = _post("sendPhoto", {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": image,
            "caption": text,
            "parse_mode": "HTML",
        })
        if ok:
            return True
        # Fall back to text-only on photo failure (image URL might be hot-linked-blocked)
        logger.info("Falling back to sendMessage after sendPhoto failed")
    return _post("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    })
