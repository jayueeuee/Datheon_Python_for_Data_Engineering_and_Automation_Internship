"""Hybrid website scraper: Requests + BeautifulSoup, with Playwright fallback.

Examples (Windows):
  py scraper.py --url https://books.toscrape.com/ --mode auto
  py scraper.py --url https://www.xbox.com/en-IN/games/browse --mode auto --pages 3
  py scraper.py --url https://example.com/products --mode playwright

Automatic mode tries normal HTTP first. If the HTML looks like a JavaScript shell
or no useful records are found, it retries the page in Chromium using Playwright.
Extraction is heuristic; complex websites may need CSS selectors supplied by the user.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
PRICE_RE = re.compile(r"(?:[$£€₹]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|GBP|EUR|INR|Rs\.?))", re.I)
NEXT_WORDS = {"next", "next page", "older", "›", "»", "→"}


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    retry = Retry(
        total=4, connect=4, read=4, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def looks_javascript_heavy(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" ", strip=True))
    scripts = len(soup.find_all("script"))
    body = soup.body
    body_children = len(body.find_all(recursive=False)) if body else 0
    app_root = bool(soup.select_one("#root, #app, #__next, [data-reactroot], [ng-version]"))
    # This is a heuristic, not proof that a site requires a browser.
    return len(text) < 250 and (scripts >= 3 or app_root or body_children <= 2)


def parse_records(html: str, page_url: str, card_selector: str | None = None,
                  title_selector: str | None = None,
                  price_selector: str | None = None) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    if card_selector:
        cards = soup.select(card_selector)
    else:
        cards = []
        # Common product/article card patterns, followed by semantic containers.
        for selector in (
            "article.product_pod", "li.product", ".product-item", "[data-testid*='product']",
            "article", ".product", ".card", "[class*='product-card']", "[class*='productCard']",
        ):
            found = soup.select(selector)
            if len(found) > len(cards):
                cards = found
        if not cards:
            cards = soup.select("main li, main article, main [role='listitem']")

    records: list[dict] = []
    for card in cards:
        title_el = card.select_one(title_selector) if title_selector else None
        if title_selector and not title_el:
            continue
        if not title_el:
            title_el = card.select_one("h1, h2, h3, h4, [itemprop='name'], a[title]")
        title = clean_text((title_el.get("title") if title_el else "") or
                           (title_el.get_text(" ", strip=True) if title_el else ""))
        if not title or len(title) > 300:
            continue

        price_el = card.select_one(price_selector) if price_selector else None
        if price_selector and not price_el:
            continue
        if not price_el:
            price_el = card.select_one("[itemprop='price'], .price, [class*='price'], [data-price]")
        card_text = clean_text(card.get_text(" ", strip=True))
        price_text = clean_text(price_el.get_text(" ", strip=True)) if price_el else ""
        if not price_text:
            match = PRICE_RE.search(card_text)
            price_text = match.group(0) if match else ""
        price_match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", price_text)
        price = float(price_match.group(0).replace(",", "")) if price_match else None

        link = title_el if title_el and title_el.name == "a" else card.select_one("a[href]")
        image = card.select_one("img[src], img[data-src]")
        records.append({
            "title": title,
            "price": price,
            "price_text": price_text,
            "metadata": card_text[:1000],
            "item_url": urljoin(page_url, link.get("href")) if link and link.get("href") else "",
            "image_url": urljoin(page_url, (image.get("src") or image.get("data-src"))) if image and (image.get("src") or image.get("data-src")) else "",
            "source_page": page_url,
            "source_domain": urlparse(page_url).netloc,
        })
    return records


def find_next_page(html: str, page_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    nxt = soup.select_one("a[rel~='next'], link[rel~='next']")
    if not nxt:
        for a in soup.select("a[href]"):
            label = clean_text(a.get("aria-label") or a.get_text(" ", strip=True)).lower()
            if label in NEXT_WORDS or label.startswith("next "):
                nxt = a
                break
    if nxt and nxt.get("href"):
        return urljoin(page_url, nxt.get("href"))
    return None


def fetch_requests(session: requests.Session, url: str) -> tuple[str, str]:
    response = session.get(url, timeout=(10, 35))
    response.raise_for_status()
    return response.text, response.url


def fetch_playwright(url: str, wait_ms: int = 1800) -> tuple[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run: py -m pip install playwright "
            "then: py -m playwright install chromium"
        ) from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(wait_ms)
            # Let lazy-loaded content appear by scrolling in small increments.
            for _ in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(350)
            html = page.content()
            final_url = page.url
        finally:
            browser.close()
    return html, final_url


def scrape(start_url: str, max_pages: int, delay: float, mode: str,
           card_selector: str | None, title_selector: str | None,
           price_selector: str | None, wait_ms: int,
           max_records: int | None = None) -> tuple[list[dict], str]:
    session = make_session()
    url = start_url
    seen_pages: set[str] = set()
    all_records: list[dict] = []
    methods_used: set[str] = set()

    for page_no in range(1, max_pages + 1):
        if not url or url in seen_pages:
            break
        seen_pages.add(url)
        logging.info("Page %s/%s: %s", page_no, max_pages, url)
        html = ""
        final_url = url
        method = mode
        if mode in ("auto", "requests"):
            try:
                html, final_url = fetch_requests(session, url)
                methods_used.add("Requests + BeautifulSoup")
            except requests.RequestException as exc:
                if mode == "requests":
                    logging.error("Requests failed: %s", exc)
                    break
                logging.warning("Requests failed (%s); trying Playwright", exc)
                method = "playwright"

        rows = []
        if html and method != "playwright":
            rows = parse_records(html, final_url, card_selector, title_selector, price_selector)
            if mode == "auto" and (not rows or looks_javascript_heavy(html)):
                logging.info("HTML appears JS-rendered or yielded no records; trying Playwright")
                method = "playwright"

        if mode == "playwright" or method == "playwright":
            try:
                html, final_url = fetch_playwright(url, wait_ms)
                methods_used.add("Playwright + BeautifulSoup")
                rows = parse_records(html, final_url, card_selector, title_selector, price_selector)
            except Exception as exc:
                logging.error("Playwright could not load %s: %s", url, exc)
                if not rows:
                    break

        if not rows:
            logging.warning("No records found on this page. Check selectors or site access.")
            break
        logging.info("Found %s records on page %s", len(rows), page_no)
        all_records.extend(rows)
        if max_records is not None and len(all_records) >= max_records:
            break
        url = find_next_page(html, final_url)
        if url:
            time.sleep(max(0, delay))

    unique: dict[str, dict] = {}
    for index, record in enumerate(all_records):
        key = record["item_url"] or f"{record['source_page']}::{record['title']}::{index}"
        unique[key] = record
    return list(unique.values()), " + ".join(sorted(methods_used)) or "No method completed"


def export_records(records: list[dict], output_dir: str, method: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if not records:
        raise RuntimeError("No records extracted. Try --mode playwright or provide CSS selectors.")
    csv_path = out / "scraped_records.csv"
    json_path = out / "scraped_records.json"
    fields = list(dict.fromkeys(k for row in records for k in row.keys()))
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "HYBRID SCRAPER REPORT", "=" * 28,
        f"Records exported: {len(records)}",
        f"Extraction method(s): {method}",
        f"Unique item URLs: {len({r['item_url'] for r in records if r['item_url']})}",
        f"Records with detected prices: {sum(r['price'] is not None for r in records)}",
        f"Records with item URLs: {sum(bool(r['item_url']) for r in records)}",
        "Note: automatic detection is heuristic; selectors may be required for some sites.",
    ]
    (out / "scrape_report.txt").write_text("\n".join(report), encoding="utf-8")
    logging.info("Saved %s and %s", csv_path, json_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape static and JavaScript-rendered pages")
    parser.add_argument("--url", default="https://books.toscrape.com/", help="Starting page URL")
    parser.add_argument("--pages", type=int, default=10, help="Maximum number of pages")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between pages in seconds")
    parser.add_argument("--mode", choices=["auto", "requests", "playwright"], default="auto")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--card-selector", help="CSS selector for each item/product card")
    parser.add_argument("--title-selector", help="CSS selector for title inside each card")
    parser.add_argument("--price-selector", help="CSS selector for price inside each card")
    parser.add_argument("--wait-ms", type=int, default=1800, help="Playwright wait after page load")
    parser.add_argument("--max-records", type=int, default=0, help="Stop after this many records (0 = no limit)")
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    if not args.url.startswith(("http://", "https://")):
        parser.error("--url must begin with http:// or https://")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.max_records < 0:
        parser.error("--max-records cannot be negative")
    records, method = scrape(args.url, args.pages, args.delay, args.mode,
                             args.card_selector, args.title_selector,
                             args.price_selector, args.wait_ms,
                             args.max_records or None)
    export_records(records, args.output_dir, method)
    print(f"\nCompleted: {len(records)} unique records")
    print(f"Method: {method}")
    print(f"Files saved in: {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
