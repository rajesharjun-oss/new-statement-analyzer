# Backend

FastAPI service for statement upload, extraction, validation, categorization, and Excel export.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in the project root or in `backend/`:

```env
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=optional_openai_key_here
ANTHROPIC_API_KEY=optional_anthropic_key_here
OCR_ENGINE=gemini
UBA_OCR_MAX_PAGES=80
UBA_AI_MAX_PAGES=30
WEMA_HEADER_SCAN_PAGES=12
ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000
MAX_UPLOAD_BYTES=20971520
TEMP_FILE_TTL_SECONDS=3600
MAX_CLASSIFY_TRANSACTIONS=500
MAX_CLASSIFY_INSTRUCTIONS_CHARS=4000
MAX_NARRATIVE_PAYLOAD_CHARS=100000
MAX_AI_REQUEST_BYTES=1048576
ENABLE_API_DOCS=false
DEBUG_ERRORS=false
```

## Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

Useful endpoints:

- `GET /health`
- `POST /analyze`
- `POST /classify-analysis`
- `POST /analysis-narrative`
- `GET /download/{file_id}`

The Vite frontend proxies these API endpoints to the backend in local development. Classification and narrative endpoints use deterministic inputs and only call an AI provider when a corresponding environment key is configured.
