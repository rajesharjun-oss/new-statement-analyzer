# LedgerSentinel — AI Bank Statement Analyzer

## Overview
LedgerSentinel is a specialized tool for extracting, validating, and categorizing transactions from Nigerian bank statements (PDF, Excel, CSV). It supports major Nigerian banks including GTBank, Access Bank, First Bank, Zenith, UBA, FCMB, WEMA, Sterling, and Providus.

## Architecture

### Frontend
- **Framework**: React 18 + TypeScript + Vite
- **UI Libraries**: Radix UI, Lucide React, Recharts
- **Port**: 5000 (dev)
- **Key files**: `App.tsx`, `index.tsx`, `index.html`, `components/`, `services/`, `types.ts`

### Backend
- **Framework**: FastAPI (Python)
- **Port**: 8000
- **Entry point**: `backend/main.py`
- **Key modules**:
  - `pdf_extractor.py` — PDF processing hub
  - `excel_extractor.py` — Excel/CSV processing
  - `categorization.py` — Transaction categorization
  - `validation.py` — Balance validation
  - `excel_generator.py` — Output Excel generation
  - `claude_service.py` — Anthropic Claude AI audit
  - `claude_extraction.py` — Claude fallback extractor
  - Bank-specific engines: `wema_engine.py`, `uba_engine.py`, etc.

## Development Workflows
- **Start application** (webview): `npm run dev` → port 5000
- **Backend** (console): `cd backend && python main.py` → port 8000
- Frontend proxies `/analyze` and `/download` API calls to the backend

## Environment Variables
See `.env.example` for required keys:
- `OPENAI_API_KEY` — OpenAI API key
- `GEMINI_API_KEY` — Google Gemini API key (also exposed as `API_KEY`)
- `ANTHROPIC_API_KEY` — (optional) Anthropic Claude for audit + fallback extraction
- `OCR_ENGINE` — OCR engine choice (`gemini` or `openai`)
- `STRICT_TEMPLATE_MODE` — Strict bank template matching (`true`/`false`)

## Deployment
- **Target**: Autoscale
- **Build**: `npm run build` (produces `dist/`)
- **Run**: `cd backend && uvicorn main:app --host=0.0.0.0 --port=8000`
- In production, FastAPI serves the React SPA from `dist/` and handles all API routes

## Features
- Bank-specific PDF extraction engines with coordinate-based parsing
- OCR fallback using Google Gemini 2.0 Flash vision
- Claude AI quality gate for low-confidence extractions
- Transaction categorization with AI fallback
- Forensic math validation (debit/credit totals reconciliation)
- Excel report generation with full transaction ledger

## Verified Bank Accuracy (production-verified)
| Bank | File | Txns | Chain Errors | Close Balance |
|------|------|------|-------------|---------------|
| GTBank | GTCO_test_1 (76-page) | 317 | 7 | 660.91 |
| Access Bank | Access2.0 (large) | 900 | 0 ✓ | 5,551,461.50 |
| FCMB | FCMB_test | 291 | 0 ✓ | 142,877,771.40 |
| Fidelity | FIDELITY_1 (ODA 51-pg) | 1161 | 0 ✓ | -157,177,336.69 |
| Fidelity | FIDELITY_2 (CAA-2) | 508 | 0 ✓ | 51,559.45 |
| Fidelity | FIDELITY_3 (ODA-3) | 1224 | 0 ✓ | 4,209,180.07 |
| Sterling | STERLING_small | 50 | 0 ✓ | 1,272,204,903.05 |
| Sterling | STERLING_large (64-pg) | 1368 | 0 ✓ | 976,471,242.60 |
| WEMA | WEMA-small | 2 | 0 ✓ | 1,626,262.53 |
| WEMA | WEMA_test (35-pg) | 423 | 62 | 1,895,627.05 |

## Key Bug Fixes Applied
- **UBA `detect_template`**: replaced `" uba "` with `\buba\b` word-boundary regex; added "date posted" as UBA fingerprint (for Q4 format)
- **UBA `detect_uba_columns`**: added "DESCRIPTION" and "DETAILS" as description-column fallbacks (for UBA Q4 + First Bank)
- **First Bank → UBA engine routing**: First Bank now routed to UBA coordinate engine (same header format)
- **Zenith `detect_zenith_columns`**: added "VAL" and "REMARKS" keyword alternates
- **Zenith word assignment**: fixed x1→x0 (x1 was shifting amounts one column right, swapping debit/credit)
- **Access word assignment**: fixed x1→x0 (same x1 right-alignment bug)
- **Fidelity unpacking**: fixed `fidelity_txns, _ = extract_fidelity_via_tables(...)` — function returns list not tuple
- **Fidelity ODA x1 for money**: large credit amounts now use x1 to avoid capture by wider description column
- **GTBank y_tol 15→12**: day+month rows (10.5 pts apart) stay together; year rows (13.9+ pts) split correctly
- **GTBank `cont_has_amounts` rescue**: 4-row date format rescue (value_date used as real date when tdate is bare month)
- **GTBank year-repair regex**: relaxed `^(20\d{2})$` → `^(20\d{2})(?:\s|$)` for "2026 18:27"-style rows
- **`parse_date_smart` time rejection**: rejects HH:MM/HH:MM:SS strings before pandas (prevents phantom today-dated transactions)
- **`parse_date_smart` bare-year rejection**: rejects 4-digit years like "2024" (prevents Sterling continuation rows from creating phantom Jan-1 transactions)
- **`parse_money` \xad negatives**: leading soft-hyphen `\xad` now treated as negative sign
- **`assign_row_to_cols` _money_re**: `\xad`-prefixed and `-`-prefixed amounts use x1 for column placement
- **Fidelity ODA balance inference**: backward pass in `merge_multiline_rows` infers B[i] = B[i+1] + D[i+1] - C[i+1]
- **Sterling phantom row fix**: Year-only continuation rows ("2024" in date column) now folded into previous transaction's description instead of creating phantom 0-amount transactions
- **WEMA bank detection fix**: WEMA now detected before UBA in `detect_template` using "withdrawals"+"deposits"+"narration" triple signal (WEMA's plural "Withdrawals"/"Deposits" columns were triggering the UBA singular check)
- **WEMA balance inference**: Forward/backward iterative inference added to `wema_engine.py` to fill B=0 holes where balance sits on a different PDF row from the transaction's date/amounts
- **Access2 date fix**: `parse_date_smart` 2-digit year resolution now always returns 2000+yr (not current year) for formats like "03-JAN-25"
- **2-stage OCR pipeline**: For scanned/image PDFs (0 text words), Gemini Vision OCRs pages to raw plain text, Claude Sonnet extracts structured transactions from that text. Standard Chartered (previously 0 txns) now yields 63 txns / 0 chain errors from 10 pages. Wired at both the generic/Ecobank fallback path and the coordinate-engine fallback path.
- **Extraction cascade order**: (1) Gemini OCR → Claude extract [scanned only], (2) Gemini single-stage multimodal, (3) Claude direct PDF, (4) legacy OCR
