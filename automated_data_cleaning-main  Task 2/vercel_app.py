from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from transform import clean_dataframe

app = FastAPI(title="Automated Data Cleaner")


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(Path(__file__).resolve().with_name("index.html"))


@app.post("/clean")
async def clean_csv(file: UploadFile = File(...)) -> dict[str, object]:
    if Path(file.filename or "").suffix.casefold() != ".csv":
        raise HTTPException(status_code=400, detail="Upload a .csv file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded CSV is empty.")

    try:
        raw = pd.read_csv(BytesIO(content))
    except (
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read the CSV: {exc}",
        ) from exc

    cleaned, report = clean_dataframe(raw)
    return {
        "input_rows": len(raw),
        "clean_rows": len(cleaned),
        "rows_removed": len(raw) - len(cleaned),
        "input_columns": [str(column) for column in raw.columns],
        "clean_columns": [str(column) for column in cleaned.columns],
        "input_preview": json.loads(
            raw.head(20).to_json(orient="records", date_format="iso")
        ),
        "clean_preview": json.loads(
            cleaned.head(20).to_json(orient="records", date_format="iso")
        ),
        "report": report,
        "cleaned_csv": cleaned.to_csv(index=False),
    }
