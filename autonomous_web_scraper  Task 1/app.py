from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from scraper import make_session, looks_javascript_heavy, parse_records, scrape

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

st.set_page_config(page_title="Smart Web Scraper", page_icon="🕸️", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 1180px;}
.hero {padding: 1.25rem 1.5rem; border: 1px solid rgba(128,128,128,.25); border-radius: 16px; margin-bottom: 1rem;}
.small-muted {font-size: .82rem; opacity: .72;}
footer {visibility: hidden;}
.corner-credit {position: fixed; right: 18px; bottom: 10px; z-index: 999; font-size: 10px; opacity: .65; background: rgba(128,128,128,.12); padding: 4px 8px; border-radius: 8px;}
</style>
<div class="hero">
  <h1>🕸️ Smart Web Scraper</h1>
  <p>Enter a website URL, detect static or dynamic pages automatically, choose how many records to collect, and download your results.</p>
</div>
""", unsafe_allow_html=True)


def check_url(raw_url: str):
    """Return (validity, message, final_url, status_code, html)."""
    value = raw_url.strip()
    if not value:
        return False, "Enter a website URL.", "", None, ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        return False, "This URL format looks incorrect. Include a valid domain, for example https://example.com.", value, None, ""
    try:
        response = make_session().get(value, timeout=(10, 25), allow_redirects=True)
        status = response.status_code
        if status in (404, 410):
            suggestion = " The page may have moved; check the path or open the site's main page." 
            if "xbox.com" in parsed.netloc.lower() and "/games/store" in parsed.path.lower():
                suggestion = " Suggested Xbox games page: https://www.xbox.com/en-IN/games/browse"
            return False, f"The server returned HTTP {status}. This page URL appears unavailable.{suggestion}", response.url, status, response.text
        if status in (401, 403, 429):
            return None, f"The site responded with HTTP {status}. The URL may exist, but access is restricted or rate-limited; this does not prove the URL is wrong.", response.url, status, response.text
        if status >= 400:
            return False, f"The server returned HTTP {status}. Check the URL or the website's availability.", response.url, status, response.text
        return True, f"URL looks reachable (HTTP {status}). Final address: {response.url}", response.url, status, response.text
    except Exception as exc:
        return None, f"Could not verify the URL because of a network, DNS, or connection issue: {exc}", value, None, ""


with st.sidebar:
    st.header("⚙️ Scraping settings")
    target_records = st.number_input("Number of records to collect", min_value=1, max_value=5000, value=100, step=10)
    max_pages = st.number_input("Maximum pages to visit", min_value=1, max_value=500, value=20, step=1)
    delay = st.slider("Delay between pages (seconds)", min_value=0.0, max_value=5.0, value=1.0, step=0.5)
    st.caption("Automatic mode tries Requests first and uses Playwright if the page appears JavaScript-rendered or no records are found.")

with st.form("scrape_form"):
    url = st.text_input("Website URL", placeholder="https://example.com/products", help="Paste the page you want to scrape. Include https:// when possible.")
    col1, col2 = st.columns(2)
    with col1:
        start_record = st.number_input("Start record (inclusive)", min_value=1, max_value=5000, value=1, step=1)
    with col2:
        end_record = st.number_input("End record (inclusive)", min_value=1, max_value=5000, value=100, step=1)
    with st.expander("Advanced: custom CSS selectors (optional)"):
        card_selector = st.text_input("Record/card selector", placeholder=".product-card")
        title_selector = st.text_input("Title selector inside each card", placeholder=".product-title")
        price_selector = st.text_input("Price selector inside each card", placeholder=".price")
    submitted = st.form_submit_button("🔎 Check URL & Start Scraping", type="primary", use_container_width=True)

if submitted:
    if start_record > end_record:
        st.error("Start record must be less than or equal to end record.")
    elif end_record > target_records:
        st.error("End record cannot be greater than the requested number of records. Increase the target count or reduce the range.")
    elif not url.strip():
        st.error("Please enter a URL first.")
    else:
        with st.spinner("Checking whether the URL is reachable..."):
            valid, message, final_url, status, initial_html = check_url(url)
        if valid is True:
            st.success("✅ URL looks correct. " + message)
        elif valid is False:
            st.error("❌ URL appears wrong or unavailable. " + message)
        else:
            st.warning("⚠️ URL could not be fully verified. " + message)

        if valid is not False:
            with st.spinner("Scraping pages... Automatic mode is active. This may take a little while."):
                try:
                    rows, method = scrape(
                        final_url or url.strip(), int(max_pages), float(delay), "auto",
                        card_selector.strip() or None,
                        title_selector.strip() or None,
                        price_selector.strip() or None,
                        1800,
                        int(end_record),
                    )
                    # Select the requested inclusive record range after deduplication.
                    selected = rows[int(start_record) - 1:int(end_record)]
                    if not selected:
                        st.warning("The page loaded, but no records were extracted. The URL may be valid while the site's HTML structure needs custom selectors or a site-specific parser.")
                        st.info("Try a category/listing page, inspect its product-card HTML, or provide CSS selectors in Advanced settings.")
                    else:
                        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                        # Save only the chosen range so the downloaded files match the range shown.
                        csv_path = OUTPUT_DIR / "scraped_records.csv"
                        json_path = OUTPUT_DIR / "scraped_records.json"
                        report_path = OUTPUT_DIR / "scrape_report.txt"
                        df = pd.DataFrame(selected)
                        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                        df.to_json(json_path, orient="records", force_ascii=False, indent=2)
                        report_path.write_text(
                            "SMART WEB SCRAPER REPORT\n" + "=" * 28 + "\n" +
                            f"Input URL: {url}\nFinal URL: {final_url}\nHTTP status during URL check: {status}\n" +
                            f"Extraction method: {method}\nRecords exported: {len(selected)}\n" +
                            f"Requested record range: {start_record}-{end_record}\n" +
                            f"Pages limit: {max_pages}\nGenerated: {datetime.now().isoformat(timespec='seconds')}\n" +
                            "Note: automatic detection is heuristic; custom selectors may be needed for some sites.\n",
                            encoding="utf-8",
                        )
                        st.session_state["scrape_result"] = {
                            "rows": selected, "method": method, "url": final_url,
                            "range": f"{start_record}-{end_record}", "files": [csv_path, json_path, report_path]
                        }
                except Exception as exc:
                    st.error(f"Scraping failed: {exc}")
                    st.caption("Check the URL, site permissions, browser installation, and CSS selectors. This tool does not bypass logins, CAPTCHAs, or access restrictions.")

result = st.session_state.get("scrape_result")
if result:
    st.divider()
    st.subheader("📊 Scraping results")
    a, b, c = st.columns(3)
    a.metric("Records extracted", len(result["rows"]))
    b.metric("Record range", result["range"])
    c.metric("Extraction mode", "Automatic")
    st.caption(f"Detected method: {result['method']} · Source: {result['url']}")
    st.dataframe(pd.DataFrame(result["rows"]), use_container_width=True, hide_index=True)

    st.subheader("📁 Output files")
    output_zip = io.BytesIO()
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in result["files"]:
            zf.write(file_path, arcname=file_path.name)
    output_zip.seek(0)
    for file_path in result["files"]:
        st.write(f"📄 {file_path.name}")
    st.download_button(
        "⬇️ Download output files (ZIP)", data=output_zip.getvalue(),
        file_name="scraper_output_files.zip", mime="application/zip",
        type="primary", use_container_width=True,
    )

    # Also package the runnable source project for convenient sharing.
    project_zip = io.BytesIO()
    with zipfile.ZipFile(project_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ["app.py", "scraper.py", "requirements.txt", "README.md"]:
            path = BASE_DIR / name
            if path.exists():
                zf.write(path, arcname=f"autonomous_web_scraper/{name}")
    project_zip.seek(0)
    st.download_button(
        "📦 Download complete scraper project (ZIP)", data=project_zip.getvalue(),
        file_name="smart_web_scraper_project.zip", mime="application/zip",
        use_container_width=True,
    )

st.markdown('<div class="corner-credit">Developed by Jay Rahane · jayrahane3115@gmail.com</div>', unsafe_allow_html=True)
