<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# LedgerSentinel Bank Statement Converter

Convert Nigerian bank statement PDFs to Excel. The application returns a single plain worksheet with source statement details and transaction columns. Dates and amounts are usable Excel values; account numbers, cheque numbers, and references remain text.

The converter does not categorize transactions or call AI providers. It checks printed totals when available and declines to create a workbook if it detects a mismatch. A workbook whose statement totals are unavailable is labeled as such in the UI. Multi-account PDFs put each account in its own section on the same worksheet.

`POST /convert` accepts multipart `file`, optional `bank` (defaults to auto-detection), and optional `password`. It returns the workbook directly with `Cache-Control: no-store`. The PDF is processed on the server in a temporary directory and deleted after parsing. A hosted instance receives the PDF during conversion; run locally for statements that must stay on your computer. The legacy analysis API is disabled by default.

## Supported Banks

- Access Bank (searchable PDFs and OCR fallback)
- UBA (searchable PDFs and OCR fallback)
- Wema Bank, including the summary cover and the repeated-summary ruled formats
- FCMB
- Keystone Bank
- Zenith Bank
- GTBank / GTCO, including multi-statement bundles
- Providus Bank
- Sterling Bank
- First Bank / FBN
- Moniepoint
- OPay

## Project Layout

- `backend/` - FastAPI API, extraction engines, validation, categorization, and Excel export.
- `components/` - React UI components.
- `services/` - Frontend API, analysis, parsing, and export helpers.
- `tests/regression/` - Structured sample expectations and regression runner.
- `tools/diagnostics/` - Legacy forensic scripts kept for future extraction debugging.
- `artifacts/debug-output/` - Local debug logs and extraction dumps. This folder is ignored by git.

## Run Locally

Prerequisites: Node.js and Python 3.10+.

1. Start the backend on `http://127.0.0.1:8000`. No API keys are required:

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

2. Start the frontend from the repository root on `http://localhost:5000`:

```bash
npm install
npm run dev
```

## Run With Docker

```bash
cp .env.example .env
docker-compose up --build
```

Open `http://localhost:8000`.

## Regression Checks

Run the application checks:

```bash
npm run typecheck
npm run test:analysis
npm run build
python -m unittest discover -s tests -p "test_*.py"
```

Add local sample statements and expected totals to `tests/regression/expected_statements.json`, then run:

```bash
python tests/regression/run_regression.py
```

Sample PDFs and spreadsheets are ignored by git, so the expectations file can describe local fixtures without committing sensitive bank statements.

The regression runner also scores description coverage, date coverage, debit/credit direction, and running-balance continuity. Add the corresponding `minimum_*` fields to each bank fixture and optionally write a CI artifact with:

```bash
python tests/regression/run_regression.py --json-report artifacts/benchmark-report.json
```

## Deploy To Render

The Dockerfile builds the React frontend and serves it through FastAPI.

Set these environment variables in Render:

- `PYTHONPATH=/app/backend`
- `ALLOWED_ORIGINS` as a comma-separated list of trusted frontend origins for cross-origin development access
- `MAX_UPLOAD_BYTES` to cap upload size, defaults to `20971520` (20MB)
- `MAX_PDF_PAGES` to cap the number of PDF pages, defaults to `700`
- `CONVERT_CONCURRENCY` to limit simultaneous conversions per process, defaults to `2`
- `ENABLE_LEGACY_ANALYSIS=false` to keep the legacy analysis and report routes disabled
- `ENABLE_API_DOCS=false` in production unless protected behind trusted access
- `DEBUG_ERRORS=false` in production so stack traces are not returned to clients

No persistent statement storage is required for the converter.
