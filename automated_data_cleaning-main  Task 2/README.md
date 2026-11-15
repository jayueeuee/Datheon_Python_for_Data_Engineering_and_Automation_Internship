# Automated Data Cleaning & Schema Transformation

## Features
- Standardizes column names.
- Parses currency values such as `₹ 1,200.50`, `$250`, and `EUR 99.00`.
- Normalizes dates using day-first parsing (change `dayfirst=True` in `transform.py` for US-style dates).
- Fills optional nulls with configured defaults.
- Rejects rows missing required fields (`order_id`, `amount`, `order_date`).
- Removes duplicate records using `order_id` as the business key.
- Enforces output data types and writes a validation log.
- Streamlit and FastAPI web interfaces preview the input/output and provide downloads.

## Setup
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run the command-line cleaner
```bash
python transform.py sample_dirty.csv --output cleaned_output.csv --report validation_report.txt
```

## Run the Streamlit app locally
```bash
streamlit run app.py
```

## Deploy to Vercel
Connect this repository to Vercel and deploy from the project root. Vercel
uses the FastAPI `app` exported from `vercel_app.py`, configured in
`pyproject.toml`.

## Run the FastAPI app locally
```bash
uvicorn vercel_app:app --reload
```
Open `http://127.0.0.1:8000` in a browser.

## Customize for another dataset
Edit `SCHEMA`, `REQUIRED_COLUMNS`, and `NULL_RULES` near the top of `transform.py`.
Update the currency/date parsing logic if your source format differs.

## Important design note
This example assumes `order_id` uniquely identifies an order and that `amount` is a single-currency numeric amount. It does not perform foreign-exchange conversion. Invalid required rows are excluded from the clean output and counted in the validation report; production workflows should additionally save rejected rows to a quarantine file.
