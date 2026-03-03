#!/usr/bin/env python3
"""
Grimsmo Saga Pen Archive Parser
Fetches all sold pen listings from grimsmoknives.com/collections/saga
and saves them to a CSV file.
"""

import csv
import html
import json
import re
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
from datetime import datetime


class HTMLListParser(HTMLParser):
    """Parse HTML list items from product body_html."""

    def __init__(self):
        super().__init__()
        self.items = []
        self._in_li = False
        self._current = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self._in_li = True
            self._current = []

    def handle_endtag(self, tag):
        if tag == "li" and self._in_li:
            text = "".join(self._current).strip()
            if text:
                self.items.append(text)
            self._in_li = False
            self._current = []

    def handle_data(self, data):
        if self._in_li:
            self._current.append(data)

    def handle_entityref(self, name):
        if self._in_li:
            entities = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
            self._current.append(entities.get(name, f"&{name};"))

    def handle_charref(self, name):
        if self._in_li:
            if name.startswith("x"):
                self._current.append(chr(int(name[1:], 16)))
            else:
                self._current.append(chr(int(name)))


def parse_details_fallback(body_html):
    """Extract text from paragraph-based HTML (older listing format using <p>/<span>/<br>)."""
    # Treat <br> and end of <p> as segment separators
    text = re.sub(r"<br\s*/?>", "\n", body_html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities and normalize non-breaking spaces
    text = html.unescape(text).replace("\xa0", " ")
    segments = [s.strip() for s in text.split("\n")]
    return " | ".join(s for s in segments if s)


def parse_details(body_html):
    """Extract bullet-point details from product HTML body."""
    if not body_html:
        return ""
    parser = HTMLListParser()
    parser.feed(body_html)
    if parser.items:
        return " | ".join(parser.items)
    # Older listings use <p>/<span>/<br> instead of <ul>/<li>
    return parse_details_fallback(body_html)


def parse_serial_number(title):
    """Extract the Saga serial number from product title like 'Saga #8841 8593850302'."""
    match = re.search(r"#(\d+)", title)
    return match.group(1) if match else ""


def parse_order_number(title):
    """Extract the order/batch number after the serial (second number in title)."""
    # Title format: "Saga #8841 8593850302"
    match = re.search(r"#\d+\s+(\d+)", title)
    return match.group(1) if match else ""


def format_date(date_str):
    """Format ISO date string to a readable date."""
    if not date_str:
        return ""
    # Remove timezone offset for parsing
    clean = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str).replace("T", " ")
    try:
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return date_str


def fetch_page(page_num, retries=4):
    """Fetch a single page from the Shopify products API."""
    url = (
        f"https://grimsmoknives.com/collections/saga/products.json"
        f"?limit=250&page={page_num}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GrimsmoArchiveParser/1.0)",
        "Accept": "application/json",
    }
    delay = 2
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("products", [])
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt < retries:
                print(f"  Retry {attempt + 1}/{retries} for page {page_num} after {delay}s ({e})")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"  Failed to fetch page {page_num}: {e}")
                return []


def parse_product(product):
    """Extract all relevant fields from a product dict."""
    title = product.get("title", "")
    handle = product.get("handle", "")
    listing_url = f"https://grimsmoknives.com/products/{handle}" if handle else ""

    # Serial and order numbers from title
    serial_number = parse_serial_number(title)
    order_number = parse_order_number(title)

    # Price from first variant
    variants = product.get("variants", [])
    price = variants[0].get("price", "") if variants else ""
    compare_at_price = variants[0].get("compare_at_price", "") if variants else ""

    # Dates
    published_at = format_date(product.get("published_at", ""))
    created_at = format_date(product.get("created_at", ""))
    updated_at = format_date(product.get("updated_at", ""))

    # Tags
    tags = ", ".join(product.get("tags", []))

    # Details from body HTML
    details = parse_details(product.get("body_html", ""))

    # Image URL (first image)
    images = product.get("images", [])
    image_url = images[0].get("src", "") if images else ""

    # Product type
    product_type = product.get("product_type", "")

    return {
        "serial_number": serial_number,
        "order_number": order_number,
        "title": title,
        "price": f"${price}" if price else "",
        "compare_at_price": f"${compare_at_price}" if compare_at_price else "",
        "date_sold": published_at,
        "date_created": created_at,
        "date_updated": updated_at,
        "tags": tags,
        "product_type": product_type,
        "details": details,
        "listing_url": listing_url,
        "image_url": image_url,
    }


def main():
    output_file = "/home/user/recipes/grimsmo_saga_archive.csv"
    fieldnames = [
        "serial_number",
        "order_number",
        "title",
        "price",
        "compare_at_price",
        "date_sold",
        "date_created",
        "date_updated",
        "tags",
        "product_type",
        "details",
        "listing_url",
        "image_url",
    ]

    total_products = 0
    page = 1

    print("Grimsmo Saga Archive Parser")
    print("=" * 50)
    print(f"Output: {output_file}")
    print()

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        while True:
            print(f"Fetching page {page}...", end=" ", flush=True)
            products = fetch_page(page)

            if not products:
                print("no products returned — done.")
                break

            rows = [parse_product(p) for p in products]
            writer.writerows(rows)
            csvfile.flush()

            count = len(products)
            total_products += count
            print(f"{count} products (total: {total_products})")

            # Shopify returns fewer than limit when on last page
            if count < 250:
                print("Last page reached.")
                break

            page += 1
            # Polite delay between requests
            time.sleep(0.5)

    print()
    print(f"Done! {total_products} products saved to {output_file}")


if __name__ == "__main__":
    main()
