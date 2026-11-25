<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# LedgerSentinel Bank Statement Analyzer

Extract, validate, categorize, and export transactions from Nigerian bank statements in PDF, Excel, and CSV formats.

Extraction and financial validation are deterministic. AI providers are optional fallbacks for difficult extraction cases and unresolved classification rows; reconciliation and quality-gate decisions never depend on an LLM.

## PDF-to-Excel Export

In the Reconciliation Workspace, choose **PDF to Excel** to convert a file without running analysis. When reviewing an imported PDF, **Export Excel** opens the same converter with the source file already selected. Existing analysis workflows and non-PDF reports are unchanged.

The converter returns one plain worksheet with statement details and original transaction columns. It does not categorize transactions or call AI providers. Dates and amounts are typed Excel values, while account, cheque, and reference numbers remain text. Password-protected PDFs prompt for a password without requiring analysis. Printed totals are checked when available; a detected mismatch prevents export.

`POST /convert` accepts multipart `file`, optional `bank`, and optional `password`. It returns the workbook directly with `Cache-Control: no-store`. A hosted instance receives the PDF during conversion and removes its temporary copy after parsing. Run locally for statements that must stay on your computer. The converter does not require provider API keys.

## Analysis Integrity

The analysis workspace checks each classified ledger for:

- Cent-accurate opening/debit/credit/closing reconciliation.
- Running-balance continuity and invalid debit/credit direction.
- Exact duplicate signatures, missing descriptions, invalid dates, and date-order anomalies.
- Classification coverage, confidence, review queue size, and source evidence coverage.
- Export provenance including source file, row/page locator, raw narration, decision source, rule, and reason.
- Monthly cash-flow trends, counterparty concentration, recurring activity, and robust amount outliers.
- Browser-local category memory learned only from explicit human review decisions.
- Optional AI narratives constrained to verified metrics and allowlisted transaction evidence IDs.

Every analysis export includes `Analysis Quality` and `Quality Issues` worksheets. A failed or review-required quality gate is an explicit signal for human review, not an automatic correction of source data.

Analysis exports also include cash-flow, monthly trend, counterparty, recurring-activity, anomaly, and evidence-backed narrative worksheets.

## Supported Banks

- Access Bank (searchable PDFs and OCR fallback)
- UBA (searchable PDFs and OCR fallback)
- Wema Bank
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

1. Create a `.env` file from the example:

```bash
cp .env.example .env
```

2. Add the API keys you use for OCR/fallback extraction:

```env
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=optional_openai_key_here
ANTHROPIC_API_KEY=optional_anthropic_key_here
```

3. Start the backend on `http://localhost:8000`:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

4. Start the frontend on `http://localhost:5000`:

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

- `GEMINI_API_KEY`
- `OPENAI_API_KEY` if OpenAI fallback is enabled
- `ANTHROPIC_API_KEY` if Claude fallback is enabled
- `PYTHONPATH=/app/backend`
- `ALLOWED_ORIGINS` as a comma-separated list of trusted frontend origins for cross-origin development access
- `MAX_UPLOAD_BYTES` to cap upload size, defaults to `20971520` (20MB)
- `MAX_PDF_PAGES` to cap converter PDF pages, defaults to `700`
- `CONVERT_CONCURRENCY` to limit simultaneous conversions per worker, defaults to `2`
- `MAX_NARRATIVE_PAYLOAD_CHARS` to cap optional AI narrative input, defaults to `100000`
- `TEMP_FILE_TTL_SECONDS` to remove stale upload/download artifacts, defaults to `3600`
- `ENABLE_API_DOCS=false` in production unless protected behind trusted access
- `DEBUG_ERRORS=false` in production so stack traces are not returned to clients

`temp_uploads/` and `temp_downloads/` are ephemeral and are cleaned by TTL. For production workloads with large files or long retention needs, attach private persistent storage with a retention policy.
