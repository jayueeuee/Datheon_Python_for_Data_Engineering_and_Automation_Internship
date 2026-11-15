"""
Automated Data Cleaning & Schema Transformation
Python 3.10+ | pandas

Run:
    python transform.py sample_dirty.csv --output cleaned_output.csv --report validation_report.txt
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from typing import Any
import pandas as pd

# Example production schema. Edit this mapping for your own dataset.
SCHEMA = {
    "order_id": "string",
    "customer_name": "string",
    "amount": "float64",
    "order_date": "datetime64[ns]",
    "currency": "string",
    "email": "string",
}

REQUIRED_COLUMNS = ["order_id", "amount", "order_date"]
NULL_RULES = {
    "customer_name": "Unknown",
    "currency": "INR",
    "email": "Not provided",
}
CURRENCY_SYMBOLS = {"₹": "", "$": "", "€": "", "£": ""}
CURRENCY_CODES = {"INR": "INR", "RS": "INR", "RS.": "INR", "USD": "USD",
                  "EUR": "EUR", "GBP": "GBP"}

def _clean_currency(value: Any) -> tuple[float | None, str | None]:
    """Extract numeric amount and currency code from values such as '₹ 1,200.50'."""
    if pd.isna(value) or str(value).strip() == "":
        return None, None
    raw = str(value).strip().upper()
    code = None
    for token, normalized in CURRENCY_CODES.items():
        if token in raw:
            code = normalized
            raw = raw.replace(token, "")
    for symbol in CURRENCY_SYMBOLS:
        if symbol in raw:
            raw = raw.replace(symbol, "")
            if symbol == "₹":
                code = code or "INR"
            elif symbol == "$":
                code = code or "USD"
            elif symbol == "€":
                code = code or "EUR"
            elif symbol == "£":
                code = code or "GBP"
    raw = raw.replace(",", "").replace(" ", "")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    try:
        return (float(raw) if raw not in {"", "-", ".", "-."} else None), code
    except ValueError:
        return None, code

def _normalize_date(series: pd.Series) -> pd.Series:
    # format="mixed" handles columns containing both ISO and slash/dash date formats (pandas 2+).
    # dayfirst=True is suitable for common Indian date formats; change if your source is US-style.
    try:
        return pd.to_datetime(series, errors="coerce", dayfirst=True, format="mixed")
    except TypeError:  # Compatibility fallback for older pandas versions.
        return series.apply(lambda value: pd.to_datetime(value, errors="coerce", dayfirst=True))

def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    original_rows = len(df)
    original_cols = list(df.columns)
    log: list[str] = []
    log.append("AUTOMATED DATA VALIDATION REPORT")
    log.append("=" * 40)
    log.append(f"Input rows: {original_rows}")
    log.append(f"Input columns: {', '.join(map(str, original_cols))}")

    # Standardize column names.
    df = df.copy()
    df.columns = (df.columns.astype(str).str.strip().str.lower()
                  .str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_"))
    log.append("Column names: trimmed, lowercased, spaces/symbols replaced with underscores.")

    missing_cols = [c for c in SCHEMA if c not in df.columns]
    extra_cols = [c for c in df.columns if c not in SCHEMA]
    for col in missing_cols:
        df[col] = pd.NA
    if missing_cols:
        log.append(f"Schema columns added as missing: {', '.join(missing_cols)}")
    if extra_cols:
        log.append(f"Extra input columns retained: {', '.join(extra_cols)}")

    # Normalize text.
    for col in ["order_id", "customer_name", "currency", "email"]:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    # Currency parsing.
    parsed = df["amount"].apply(_clean_currency)
    df["amount"] = pd.to_numeric(parsed.apply(lambda x: x[0]), errors="coerce")
    parsed_codes = parsed.apply(lambda x: x[1]).astype("string")
    df["currency"] = parsed_codes.fillna(df["currency"])
    df["currency"] = df["currency"].str.upper().replace({"RS": "INR", "RS.": "INR"})
    df["currency"] = df["currency"].fillna(NULL_RULES["currency"])

    # Dates.
    before_bad_dates = int(df["order_date"].notna().sum())
    df["order_date"] = _normalize_date(df["order_date"])
    bad_dates = before_bad_dates - int(df["order_date"].notna().sum())
    log.append(f"Unparseable dates converted to null: {bad_dates}")

    # Email normalization.
    df["email"] = df["email"].str.lower()

    # Null handling: required fields remain null and are rejected; optional fields get defaults.
    for col, default in NULL_RULES.items():
        nulls = int(df[col].isna().sum())
        if nulls:
            df[col] = df[col].fillna(default)
            log.append(f"Filled {nulls} null value(s) in '{col}' with '{default}'.")
    required_nulls = {c: int(df[c].isna().sum()) for c in REQUIRED_COLUMNS}
    invalid_required = df[REQUIRED_COLUMNS].isna().any(axis=1)
    rejected = df.loc[invalid_required].copy()
    df = df.loc[~invalid_required].copy()
    log.append(f"Rows rejected for missing/invalid required fields: {len(rejected)}")
    if required_nulls:
        log.append("Required-field null counts before rejection: " +
                   ", ".join(f"{k}={v}" for k, v in required_nulls.items()))

    # Remove duplicate records using the business key.
    before_dedupe = len(df)
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    duplicates = before_dedupe - len(df)
    log.append(f"Duplicate order_id records removed: {duplicates}")

    # Enforce types and order.
    df["order_id"] = df["order_id"].astype("string")
    df["customer_name"] = df["customer_name"].astype("string")
    df["amount"] = df["amount"].astype("float64")
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["currency"] = df["currency"].astype("string")
    df["email"] = df["email"].astype("string")
    output_cols = list(SCHEMA) + extra_cols
    df = df[output_cols].reset_index(drop=True)

    # Final validation.
    final_errors = []
    for col in REQUIRED_COLUMNS:
        if df[col].isna().any():
            final_errors.append(f"Required column '{col}' contains nulls.")
    if df["order_id"].duplicated().any():
        final_errors.append("order_id is not unique.")
    if not pd.api.types.is_numeric_dtype(df["amount"]):
        final_errors.append("amount is not numeric.")
    if not pd.api.types.is_datetime64_any_dtype(df["order_date"]):
        final_errors.append("order_date is not datetime.")
    log.append(f"Output rows: {len(df)}")
    log.append(f"Rows removed/rejected: {original_rows - len(df)}")
    log.append(f"Final validation: {'PASSED' if not final_errors else 'FAILED'}")
    if final_errors:
        log.extend("ERROR: " + e for e in final_errors)
    else:
        log.append("All required fields, uniqueness, and data types passed.")
    if len(rejected):
        log.append("Rejected rows are not included in cleaned output; review source data to repair them.")
    return df, "\n".join(log)

def main():
    parser = argparse.ArgumentParser(description="Clean and validate a CSV dataset.")
    parser.add_argument("input", help="Input CSV path")
    parser.add_argument("--output", default="cleaned_output.csv")
    parser.add_argument("--report", default="validation_report.txt")
    args = parser.parse_args()
    raw = pd.read_csv(args.input)
    cleaned, report = clean_dataframe(raw)
    cleaned.to_csv(args.output, index=False)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved: {args.output} and {args.report}")

if __name__ == "__main__":
    main()
