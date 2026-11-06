#!/usr/bin/env python3
"""
mdcomputers_scraper.py
----------------------
Extracts product listings from MD Computers (https://mdcomputers.in) for any
search term.

The site runs on OpenCart, so search results live at:

    https://mdcomputers.in/?route=product/search&search=<term>&page=<n>

Every result card is a `div.product-grid-item`. Inside each card:
  * h3.product-entities-title a  -> product name + product URL
  * span.price span.ins .amount  -> current selling price  (e.g. "₹9,160")
  * span.price span.del .amount  -> original / struck-through price
  * span.onsale.product-label    -> discount label (e.g. "-8%") if present

Search results are paginated (20 per page); the page links live in
`ul.pagination`. We follow the numbered page links until no new products are
found.

Usage:
    python mdcomputers_scraper.py "external harddrive"
    python mdcomputers_scraper.py "gaming keyboard" --pages 2 --format csv -o out.csv

Requires:  Python 3.9+ and the packages in requirements.txt
           (pip install -r requirements.txt  ->  requests, beautifulsoup4)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mdcomputers.in"
SEARCH_PATH = "/"

# Chrome-style user agent: the site behaves like a normal browser for us, and
# we identify ourselves honestly in the request header.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
        "mdcomputers-product-scraper/1.0 (educational take-home exercise)"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

PAUSE_BETWEEN_PAGES = 1.0  # seconds; be polite to the server
HTTP_TIMEOUT = 30

PRICE_RE = re.compile(r"[\d,]+")  # pulls "9,160" out of "₹9,160"


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def build_search_url(term: str, page: int) -> str:
    query = urllib.parse.urlencode(
        {"route": "product/search", "search": term, "page": page}
        if page > 1
        else {"route": "product/search", "search": term},
        quote_via=urllib.parse.quote_plus,
    )
    return f"{BASE_URL}{SEARCH_PATH}?{query}"


def fetch_page(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def _parse_price(text: str | None) -> int | None:
    """'₹9,160' -> 9160 (int rupees). Returns None when no price is present."""
    if not text:
        return None
    match = PRICE_RE.search(text)
    return int(match.group().replace(",", "")) if match else None


def parse_card(card) -> dict | None:
    """Extract the fields we care about from one .product-grid-item card."""
    title_tag = card.select_one("h3.product-entities-title a")
    if title_tag is None:  # not a product card (e.g. a stray banner)
        return None

    price_block = card.select_one("span.price")
    current = old = None
    if price_block:
        current = _parse_price(
            price_block.select_one("span.ins .amount").get_text(" ", strip=True)
            if price_block.select_one("span.ins .amount")
            else None
        )
        old = _parse_price(
            price_block.select_one("span.del .amount").get_text(" ", strip=True)
            if price_block.select_one("span.del .amount")
            else None
        )

    discount_label = card.select_one("span.onsale.product-label")

    return {
        "name": title_tag.get_text(" ", strip=True),
        "url": title_tag.get("href", ""),
        "current_price": current,
        "original_price": old,
        "discount": discount_label.get_text(strip=True) if discount_label else None,
    }


def parse_page(soup: BeautifulSoup) -> list[dict]:
    products = []
    for card in soup.select("div.product-grid-item"):
        parsed = parse_card(card)
        if parsed:
            products.append(parsed)
    return products


def parse_pagination(soup: BeautifulSoup) -> list[int]:
    """Return the page numbers the results bar links to (numeric links only).

    `>` and `>|` are navigation arrows, so only pure-digit link texts count.
    """
    numbers = []
    for link in soup.select("ul.pagination a.page-link"):
        text = link.get_text(strip=True)
        if text.isdigit():
            numbers.append(int(text))
    return sorted(set(numbers))


# --------------------------------------------------------------------------
# Crawling
# --------------------------------------------------------------------------
def search_products(term: str, max_pages: int | None = None) -> list[dict]:
    """Walk every results page for `term` and return all unique products."""
    session = requests.Session()
    products: list[dict] = []
    seen_urls: set[str] = set()

    page = 1
    while True:
        url = build_search_url(term, page)
        print(f"[fetch] page {page}: {url}", file=sys.stderr)

        soup = fetch_page(session, url)
        cards = parse_page(soup)

        # A product URL can appear twice in one page (duplicated promo card);
        # add each URL to the seen-set as we go so both cross-page *and*
        # within-page duplicates are filtered.
        new_items = []
        for product in cards:
            if product["url"] not in seen_urls:
                seen_urls.add(product["url"])
                new_items.append(product)
        products.extend(new_items)

        next_pages = [n for n in parse_pagination(soup) if n > page]
        if not next_pages or not new_items:
            break  # last page / nothing new -> stop
        if max_pages is not None and page >= max_pages:
            print(f"[stop] reached --pages limit of {max_pages}", file=sys.stderr)
            break
        page = min(next_pages)
        time.sleep(PAUSE_BETWEEN_PAGES)  # rate limiting: hand browsers a break

    return products


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def write_json(products: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"count": len(products), "products": products}, fh, indent=2, ensure_ascii=False)


def write_csv(products: list[dict], path: str) -> None:
    fields = ["name", "current_price", "original_price", "discount", "url"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(products)


def print_table(products: list[dict]) -> None:
    if not products:
        print("No products found.")
        return
    width = max(len(p["name"]) for p in products)
    for p in products:
        price = f"₹{p['current_price']:,}" if p["current_price"] else "n/a"
        old = f" (was ₹{p['original_price']:,})" if p["original_price"] else ""
        flag = f" [{p['discount']}]" if p["discount"] else ""
        print(f"{p['name']:<{width}}  {price}{old}{flag}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy code page (cp1252) that cannot
    # encode "₹"; force UTF-8 output so `--format table`/csv/json to stdout
    # never crash on unicode. backslashreplace keeps output alive even on
    # terminals that cannot render the glyphs.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(
        description="Fetch MD Computers search results for a product term."
    )
    parser.add_argument("search_term", help="e.g. 'external harddrive'")
    parser.add_argument("--pages", type=int, default=None,
                        help="cap on results pages (default: all)")
    parser.add_argument("--format", choices=["json", "csv", "table"],
                        default="json", help="output format (default: json)")
    parser.add_argument("-o", "--output", default=None,
                        help="write to a file instead of stdout")
    args = parser.parse_args(argv)

    try:
        products = search_products(args.search_term, args.pages)
    except requests.RequestException as exc:
        print(f"error: could not reach mdcomputers.in ({exc})", file=sys.stderr)
        return 1

    if args.output:
        (write_json if args.format == "json" else write_csv)(products, args.output)
        print(f"[done] wrote {len(products)} products to {args.output}", file=sys.stderr)
    elif args.format == "table":
        print_table(products)
    elif args.format == "csv":
        if not products:
            return 0
        writer = csv.DictWriter(sys.stdout, fieldnames=list(products[0]))
        writer.writeheader()
        writer.writerows(products)
    else:  # json to stdout
        print(json.dumps({"count": len(products), "products": products},
                         indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
