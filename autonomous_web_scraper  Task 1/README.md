# Autonomous Web Scraper & Data Extractor

A Python scraper that supports ordinary HTML pages and JavaScript-rendered pages using:

- **Requests** for fast HTTP downloads and retry handling
- **BeautifulSoup4** for HTML parsing
- **Playwright (Chromium)** as a browser fallback for JavaScript-rendered content
- CSV and JSON export, plus a scrape report

## 1. Install on Windows

Open PowerShell in this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m playwright install chromium
```

If PowerShell blocks activation, run the commands without activating the environment:

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
```

## 2. Run with automatic detection

```powershell
py scraper.py --url https://books.toscrape.com/ --mode auto --pages 10
```

`auto` first downloads the page with Requests. If it detects a likely JavaScript shell or finds no records, it retries with Playwright. Both paths use BeautifulSoup to extract data.

## 3. Choose a mode manually

```powershell
# Static HTML only
py scraper.py --url https://books.toscrape.com/ --mode requests --pages 5

# Render the page in Chromium
py scraper.py --url https://example.com/catalog --mode playwright --pages 3
```

## 4. Use custom CSS selectors

Automatic card detection is a best-effort heuristic. For a site with a different layout, inspect its HTML and pass selectors:

```powershell
py scraper.py --url https://example.com/catalog --mode auto --pages 3 --card-selector ".product-card" --title-selector ".product-title" --price-selector ".price"
```

Selectors are examples only; replace them with selectors that actually exist on the target page. `--title-selector` and `--price-selector` are optional.

## 5. Output

The `output` folder contains:

- `scraped_records.csv`
- `scraped_records.json`
- `scrape_report.txt`

Each record can contain title, detected numeric price and price text, card metadata, item URL, image URL, source page, and source domain. A price may be blank when the site does not expose one.

## 6. Important limitations

- Automatic detection is heuristic, not universal. Websites use different page structures, selectors, APIs, lazy loading, and pagination patterns.
- Playwright can render client-side JavaScript, but it does not magically know which elements are the records. Some sites still need custom CSS selectors or a site-specific parser.
- The current pagination logic follows a visible `rel=next` link or a link labelled “Next”. Infinite-scroll sites and unusual pagination may need custom handling.
- Some sites block automated traffic or require authentication. This project does not bypass CAPTCHAs, logins, paywalls, or technical access controls.
- Before scraping, check the site's terms, robots.txt, and applicable laws. Use reasonable delays and collect only data you are permitted to access.

## 7. Streamlit front end

Run the visual interface on Windows:

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
py -m streamlit run app.py
```

In the browser interface, enter a URL, choose the target record count and inclusive record range, then start scraping. The app checks URL reachability, runs automatic Requests/Playwright detection, previews extracted records, and offers ZIP downloads for the output files and runnable project. A reachable URL does not guarantee that generic selectors can identify its records; some sites need custom selectors.

## 8. Testing URLs (10 practice pages)

Use these public practice websites to test the scraper. They are intended for learning and testing; page structure and availability can change.

### Static HTML pages — try `--mode requests` first

1. **Books to Scrape** — book cards, prices, ratings, and pagination  
   https://books.toscrape.com/

2. **Fake Python Jobs** — job listing cards  
   https://realpython.github.io/fake-jobs/

3. **Quotes to Scrape** — quotes, authors, and tags  
   https://quotes.toscrape.com/

4. **Scrape This Site: Countries** — country names, capitals, and populations  
   https://www.scrapethissite.com/pages/simple/

5. **Scrape This Site: Hockey Teams** — team statistics and pagination  
   https://www.scrapethissite.com/pages/forms/

### JavaScript/browser test pages — try `--mode auto` or `--mode playwright`

6. **Quotes to Scrape: JavaScript version** — content rendered by JavaScript  
   https://quotes.toscrape.com/js/

7. **Quotes to Scrape: Infinite scroll** — content loaded while scrolling  
   https://quotes.toscrape.com/scroll

8. **Quotes to Scrape: Delayed JavaScript** — content appears after a delay  
   https://quotes.toscrape.com/js-delayed/

9. **The Internet: Dynamic Loading** — content loaded after a button/action  
   https://the-internet.herokuapp.com/dynamic_loading/1

10. **The Internet: Infinite Scroll** — repeated content loaded during scrolling  
    https://the-internet.herokuapp.com/infinite_scroll/

### Example test commands

```powershell
# Static page
py scraper.py --url https://books.toscrape.com/ --mode requests --pages 2

# JavaScript-rendered page
py scraper.py --url https://quotes.toscrape.com/js/ --mode auto --pages 1

# Delayed JavaScript page
py scraper.py --url https://quotes.toscrape.com/js-delayed/ --mode playwright --pages 1
```

**Testing note:** A URL opening successfully only confirms that the page is reachable. It does not guarantee that the scraper's generic card detector will identify records. Infinite-scroll pages may need explicit scrolling, and button-driven pages may need click/wait logic. If a test page returns no records, inspect its HTML and configure suitable selectors or site-specific handling.
