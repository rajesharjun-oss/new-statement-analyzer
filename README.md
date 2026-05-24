<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# AI Bank Statement Analyzer

Extract, validate, categorize, and export transactions from Nigerian bank statements in PDF, Excel, and CSV formats.

## Supported Banks

- Access Bank (searchable PDFs and OCR fallback)
- UBA (searchable PDFs and OCR fallback)
- Wema Bank
- FCMB
- Zenith Bank
- GTBank / GTCO, including multi-statement bundles
- Providus Bank
- Sterling Bank
- First Bank / FBN

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

Add local sample statements and expected totals to `tests/regression/expected_statements.json`, then run:

```bash
python tests/regression/run_regression.py
```

Sample PDFs and spreadsheets are ignored by git, so the expectations file can describe local fixtures without committing sensitive bank statements.

## Deploy To Render

The Dockerfile builds the React frontend and serves it through FastAPI.

Set these environment variables in Render:

- `GEMINI_API_KEY`
- `OPENAI_API_KEY` if OpenAI fallback is enabled
- `ANTHROPIC_API_KEY` if Claude fallback is enabled
- `PYTHONPATH=/app/backend`

`temp_uploads/` and `temp_downloads/` are ephemeral. For production workloads with large files or long retention needs, attach persistent storage.
