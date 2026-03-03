#!/usr/bin/env python3
"""
MachineWise Rota Pen Archive Parser
Fetches current pen listings from machinewise.store/products/rota
and saves them to a CSV file.

NOTE: The Rota uses Shopify variants (one product, many serial numbers).
Sold pens are *deleted* as variants and cannot be recovered from the live
store or the Shopify API. This script captures currently available
(unsold) pens only.
"""

import csv
import html
import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime


BASE_URL = "https://machinewise.store"
PRODUCT_HANDLE = "rota"
OUTPUT_FILE = "/home/user/recipes/machinewise_rota_archive.csv"


def format_date(date_str):
    """Format ISO date string to a readable local datetime."""
    if not date_str:
        return ""
    clean = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str).replace("T", " ")
    try:
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return date_str


def parse_body_text(body_html):
    """Strip HTML tags and return plain text from body_html."""
    if not body_html:
        return ""
    text = re.sub(r"<br\s*/?>", " ", body_html, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|h\d|li)>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def fetch_product(retries=4):
    """Fetch the Rota product JSON from the Shopify store."""
    url = f"{BASE_URL}/products/{PRODUCT_HANDLE}.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RotaArchiveParser/1.0)",
        "Accept": "application/json",
    }
    delay = 2
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8")).get("product", {})
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt < retries:
                print(f"  Retry {attempt + 1}/{retries} after {delay}s ({e})")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"  Failed to fetch product: {e}")
                return {}


def parse_variant(variant, img_map, tags, details):
    """Extract all relevant fields from a variant dict."""
    serial = variant.get("option1", "")
    variant_id = variant.get("id", "")
    price = variant.get("price", "")
    compare_at = variant.get("compare_at_price", "")
    created_at = format_date(variant.get("created_at", ""))
    updated_at = format_date(variant.get("updated_at", ""))
    image_url = img_map.get(variant.get("image_id"), "")
    product_url = (
        f"{BASE_URL}/products/{PRODUCT_HANDLE}?variant={variant_id}"
        if variant_id
        else ""
    )

    return {
        "serial_number": serial,
        "variant_id": variant_id,
        "price": f"${price}" if price else "",
        "compare_at_price": f"${compare_at}" if compare_at else "",
        "date_listed": created_at,
        "date_updated": updated_at,
        "tags": tags,
        "details": details,
        "product_url": product_url,
        "image_url": image_url,
    }


def main():
    print("MachineWise Rota Archive Parser")
    print("=" * 50)
    print(f"Output: {OUTPUT_FILE}")
    print()
    print("Note: Sold pens are deleted as Shopify variants and are not")
    print("recoverable from the live store. Only available pens are captured.")
    print()

    product = fetch_product()
    if not product:
        print("Failed to fetch product data. Exiting.")
        return

    variants = product.get("variants", [])
    images = product.get("images", [])
    img_map = {img["id"]: img["src"] for img in images}
    tags = ", ".join(product.get("tags", []))
    details = parse_body_text(product.get("body_html", ""))

    fieldnames = [
        "serial_number",
        "variant_id",
        "price",
        "compare_at_price",
        "date_listed",
        "date_updated",
        "tags",
        "details",
        "product_url",
        "image_url",
    ]

    rows = [parse_variant(v, img_map, tags, details) for v in variants]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done! {len(rows)} pens saved to {OUTPUT_FILE}")
    if rows:
        serials = [r["serial_number"] for r in rows]
        print(f"Serial numbers captured: {serials[0]} – {serials[-1]}")


if __name__ == "__main__":
    main()
