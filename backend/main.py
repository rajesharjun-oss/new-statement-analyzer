from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import asyncio
import os
import sys
import uuid
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load environment variables from .env file
load_dotenv()

# Make backend modules importable both when the app is started as
# `uvicorn main:app` from backend/ and as `uvicorn backend.main:app`
# from the repository root or a platform start command.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pdf_extractor import extract_transactions
from excel_extractor import extract_excel_transactions
from validation import validate_totals
from categorization import categorize_transactions
from excel_generator import generate_excel
from claude_service import generate_audit_summary
from statement_conversion import ConversionError, XLSX_MIME, convert_pdf

ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() == "true"
app = FastAPI(
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

class AIClassifyTransaction(BaseModel):
    id: str
    date: Optional[str] = None
    description: str
    debit: Optional[float] = 0
    credit: Optional[float] = 0
    reference: Optional[str] = None

class AIClassifyRequest(BaseModel):
    transactions: List[AIClassifyTransaction]
    template: Dict[str, Any]
    customInstructions: Optional[str] = ""


class AINarrativeRequest(BaseModel):
    insights: Dict[str, Any]
    quality: Dict[str, Any]
    deterministicNarrative: Dict[str, Any]
    allowedEvidenceIds: List[str]

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Backend is reachable"}

def csv_env(name: str, default: str) -> List[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]

# CORS is intentionally explicit. Same-origin production traffic does not need
# CORS, and credentialed wildcard CORS is unsafe for an internet-facing API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=csv_env("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(value, minimum)

UPLOAD_DIR = Path("temp_uploads")
DOWNLOAD_DIR = Path("temp_downloads")
UPLOAD_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_BYTES = env_int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)
MAX_PDF_PAGES = env_int("MAX_PDF_PAGES", 700)
CONVERT_CONCURRENCY = env_int("CONVERT_CONCURRENCY", 2)
TEMP_FILE_TTL_SECONDS = env_int("TEMP_FILE_TTL_SECONDS", 60 * 60)
MAX_CLASSIFY_TRANSACTIONS = env_int("MAX_CLASSIFY_TRANSACTIONS", 500)
MAX_CLASSIFY_INSTRUCTIONS_CHARS = env_int("MAX_CLASSIFY_INSTRUCTIONS_CHARS", 4000)
MAX_NARRATIVE_PAYLOAD_CHARS = env_int("MAX_NARRATIVE_PAYLOAD_CHARS", 100_000)
MAX_AI_REQUEST_BYTES = env_int("MAX_AI_REQUEST_BYTES", 1_048_576)
RATE_LIMIT_WINDOW_SECONDS = env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
ANALYZE_RATE_LIMIT = env_int("ANALYZE_RATE_LIMIT", 20)
CLASSIFY_RATE_LIMIT = env_int("CLASSIFY_RATE_LIMIT", 30)
NARRATIVE_RATE_LIMIT = env_int("NARRATIVE_RATE_LIMIT", 10)
SUPPORTED_FILE_EXTS = {".pdf", ".xlsx", ".xls", ".csv"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
FILE_SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xls": (b"\xd0\xcf\x11\xe0",),
}

# Mount static files (React build)
# Check multiple potential dist locations for production
DIST_DIR = Path("/app/dist")
if not DIST_DIR.exists():
    # Fallback to relative path if running as a native Web Service on Render or locally
    DIST_DIR = Path(__file__).parent.parent / "dist"

if DIST_DIR.exists():
    # Ensure Assets subdirectory exists before mounting
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

def cleanup_stale_temp_files() -> None:
    now = time.time()
    for directory in (UPLOAD_DIR, DOWNLOAD_DIR):
        try:
            for path in directory.iterdir():
                if path.is_file() and now - path.stat().st_mtime > TEMP_FILE_TTL_SECONDS:
                    path.unlink(missing_ok=True)
        except Exception as exc:
            print(f"WARN: Temp cleanup failed for {directory}: {exc}")

def validate_upload_content(file_ext: str, content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        max_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File is too large. Maximum allowed size is {max_mb:.0f}MB")

    signatures = FILE_SIGNATURES.get(file_ext)
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise HTTPException(status_code=400, detail="File content does not match the declared file type")
    if file_ext == ".csv" and b"\x00" in content[:4096]:
        raise HTTPException(status_code=400, detail="CSV upload appears to contain binary data")

@app.on_event("startup")
async def startup_cleanup():
    cleanup_stale_temp_files()


request_buckets: Dict[str, List[float]] = {}
convert_slots = asyncio.Semaphore(CONVERT_CONCURRENCY)


@app.middleware("http")
async def reject_oversized_conversions(request: Request, call_next):
    path = request.url.path.rstrip("/")
    if path == "/convert" and request.method == "POST":
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_UPLOAD_BYTES + 65536:
            return JSONResponse(status_code=413, content={"detail": "The PDF is too large."})
    return await call_next(request)


@app.middleware("http")
async def reject_oversized_ai_requests(request: Request, call_next):
    if request.method == "POST" and request.url.path in {"/classify-analysis", "/analysis-narrative"}:
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if content_length > MAX_AI_REQUEST_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body is too large."},
                headers={"Cache-Control": "no-store"},
            )
    return await call_next(request)


@app.middleware("http")
async def rate_limit_expensive_routes(request: Request, call_next):
    route_limits = {
        "/convert": ANALYZE_RATE_LIMIT,
        "/analyze": ANALYZE_RATE_LIMIT,
        "/classify-analysis": CLASSIFY_RATE_LIMIT,
        "/analysis-narrative": NARRATIVE_RATE_LIMIT,
    }
    limit = route_limits.get(request.url.path)
    if limit and request.method == "POST":
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client}"
        recent = [timestamp for timestamp in request_buckets.get(key, []) if now - timestamp < RATE_LIMIT_WINDOW_SECONDS]
        if len(recent) >= limit:
            retry_after = max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - recent[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Request limit exceeded. Retry later."},
                headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
            )
        recent.append(now)
        request_buckets[key] = recent
    return await call_next(request)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.path.startswith(("/convert", "/analyze", "/download", "/classify-analysis", "/analysis-narrative")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response

def num(x):
    """Safely convert to float, handling strings with commas"""
    try:
        return float(str(x).replace(",", ""))
    except:
        return 0.0

def normalize_bank_id(bank: str) -> str:
    value = (bank or "auto").strip().lower()
    aliases = {
        "accessbank": "access",
        "access_bank": "access",
        "access-bank": "access",
        "access bank": "access",
        "monie point": "moniepoint",
        "moniepoint bank": "moniepoint",
        "moniepoint mfb": "moniepoint",
        "o pay": "opay",
    }
    return aliases.get(value, value)


@app.post("/convert")
async def convert_statement(
    file: UploadFile = File(...),
    bank: str = Form("auto", max_length=40),
    password: str = Form(""),
):
    allowed_banks = {
        "auto", "gtbank", "gtco", "ecobank", "access", "fidelity", "apt_securities", "uba",
        "firstbank", "zenith", "wema", "providus", "fcmb", "keystone", "sterling",
        "standard_chartered", "moniepoint", "opay",
    }
    selected = normalize_bank_id(bank)
    if selected not in allowed_banks:
        raise HTTPException(status_code=400, detail="Select a supported issuing bank.")
    if len(password) > 256:
        raise HTTPException(status_code=400, detail="The PDF password is too long.")
    if Path(file.filename or "").suffix.lower() != ".pdf" or file.content_type not in {
        "application/pdf", "application/octet-stream", None,
    }:
        raise HTTPException(status_code=400, detail="Only PDF bank statements are supported.")
    if convert_slots.locked():
        raise HTTPException(status_code=503, detail="The converter is busy. Try again shortly.", headers={"Retry-After": "10"})

    async with convert_slots:
        try:
            content = await file.read(MAX_UPLOAD_BYTES + 1)
            validate_upload_content(".pdf", content)
            workbook, count, verified = await asyncio.to_thread(convert_pdf, content, selected, password, MAX_PDF_PAGES)
        except ConversionError as exc:
            raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
        except HTTPException:
            raise
        except Exception as exc:
            print(f"WARN: Converter failed ({type(exc).__name__}).")
            raise HTTPException(status_code=500, detail="Conversion failed. Try again with the original statement PDF.") from exc
        finally:
            await file.close()

    return Response(content=workbook, media_type=XLSX_MIME, headers={
        "Content-Disposition": 'attachment; filename="statement.xlsx"',
        "Cache-Control": "no-store",
        "X-Transaction-Count": str(count),
        "X-Statement-Check": "matched" if verified else "unavailable",
    })


def access_result_score(result: dict) -> tuple:
    txns = result.get("transactions") or []
    meta = result.get("metadata") or {}
    validation = validate_totals(txns, meta)
    return (
        1 if validation.get("totals_match") is True else 0,
        1 if meta.get("statement_total_debit") is not None and meta.get("statement_total_credit") is not None else 0,
        len(txns),
    )

@app.post("/analyze")
async def analyze_statement(
    request: Request,
    file: UploadFile = File(...),
    bank: str = Form("auto")  # auto, gtbank, accessbank, firstbank, zenith, uba, etc.
):
    request_started = time.perf_counter()
    print(f"\n{'!'*40}")
    normalized_bank = normalize_bank_id(bank)
    filename_lower = (file.filename or "").lower()
    access_upload_hint = normalized_bank == "access" or "access" in filename_lower

    print(f"!!! [ANALYZE-FORENSIC] Request received: {file.filename} (Bank: {bank} -> {normalized_bank}) !!!")
    print(f"{'!'*40}\n")
    """
    Main endpoint: accepts PDF, returns summary + download URL
    
    Parameters:
    - file: PDF bank statement
    - bank: Optional bank identifier (auto, gtbank, accessbank, firstbank, zenith, uba)
           Defaults to 'auto' for automatic detection
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in SUPPORTED_FILE_EXTS:
        raise HTTPException(status_code=400, detail="Only PDF, Excel (.xlsx, .xls), and CSV files are supported")

    file_id = str(uuid.uuid4())
    stored_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    excel_path = DOWNLOAD_DIR / f"statement-analysis-{file_id}.xlsx"

    try:
        cleanup_stale_temp_files()
        content = await file.read()
        print(f"  [FORENSIC] Upload Buffer Size: {len(content)} bytes")
        validate_upload_content(file_ext, content)
        stored_path.write_bytes(content)

        # Step 1: Extract transactions (Non-blocking background thread)
        import asyncio
        if file_ext == ".pdf":
            extraction_started = time.perf_counter()
            statement_results = await asyncio.to_thread(extract_transactions, stored_path, bank_identifier=normalized_bank)
            print(
                "INFO [ANALYZE-TIMING] "
                f"extraction={time.perf_counter() - extraction_started:.2f}s "
                f"requested_bank={normalized_bank}"
            )

            # Access PDFs must not be allowed to surface a weaker generic parse.
            # On Cloud Run, auto-detection can occasionally choose a partial path
            # before the Access coordinate engine wins locally.
            if access_upload_hint:
                try:
                    access_results = await asyncio.to_thread(extract_transactions, stored_path, bank_identifier="access")
                    access_candidates = [r for r in access_results if r.get("transactions")]
                    if access_candidates:
                        best_access = max(access_candidates, key=access_result_score)
                        current_candidates = [r for r in statement_results if r.get("transactions")]
                        best_current = max(current_candidates, key=access_result_score) if current_candidates else None
                        if best_current is None or access_result_score(best_access) > access_result_score(best_current):
                            print(
                                "WARN: Access primary route replaced weaker parse "
                                f"({len(best_current.get('transactions', [])) if best_current else 0} -> "
                                f"{len(best_access.get('transactions', []))} transactions)."
                            )
                            statement_results = [best_access]
                except Exception as e:
                    print(f"WARN: Access primary route failed before validation: {e}")
        else:
            # Excel/CSV handling
            txns, meta = await asyncio.to_thread(extract_excel_transactions, stored_path)
            statement_results = [{"transactions": txns, "metadata": meta}]

        # Step 1b: QUALITY GATE — Claude fallback for bad extractions
        if file_ext == '.pdf' and os.getenv('ANTHROPIC_API_KEY'):
            for i, stmt in enumerate(statement_results):
                txns = stmt.get("transactions", [])
                meta = stmt.get("metadata", {})
                detected_bank = meta.get('bank', 'generic')

                needs_claude = False
                reason = ""

                # Condition 1: Zero transactions
                if not txns:
                    needs_claude = True
                    reason = "0 transactions extracted"

                # Condition 2: High empty description rate (>25%)
                elif txns:
                    empty_count = sum(1 for t in txns if not (t.get('description') or t.get('remarks') or '').strip())
                    if len(txns) > 0 and empty_count / len(txns) > 0.25:
                        needs_claude = True
                        reason = f"{empty_count}/{len(txns)} empty descriptions"

                # Condition 3: Unknown bank with no transactions
                if detected_bank == 'generic' and not txns:
                    needs_claude = True
                    reason = "unknown bank template"

                if needs_claude and not meta.get('_claude_retried'):
                    print(f"QUALITY GATE: Triggering Claude extraction fallback. Reason: {reason}")
                    try:
                        from claude_extraction import extract_with_claude
                        claude_txns = await asyncio.to_thread(extract_with_claude, str(stored_path))
                        if claude_txns and len(claude_txns) > len(txns):
                            print(f"QUALITY GATE: Claude returned {len(claude_txns)} txns (vs {len(txns)} original). Using Claude results.")
                            from pdf_extractor import normalize_remarks
                            statement_results[i] = {
                                "transactions": normalize_remarks(claude_txns),
                                "metadata": {**meta, "_claude_retried": True, "method": "claude_fallback"}
                            }
                    except Exception as e:
                        print(f"QUALITY GATE: Claude fallback failed: {e}")

        processed_statements = []
        for stmt in statement_results:
            txns = stmt.get("transactions", [])
            meta = stmt.get("metadata", {})
            
            # Step 2: Validate totals
            validation_result = validate_totals(txns, meta)

            # Access-only guard: do not surface a partial Access parse when the
            # printed statement totals are available. Retry through the dedicated
            # Access route and keep the candidate only if it validates cleanly.
            if (
                file_ext == ".pdf"
                and (meta.get("bank") == "access" or access_upload_hint)
                and validation_result.get("totals_match") is False
                and meta.get("statement_total_debit") is not None
                and meta.get("statement_total_credit") is not None
            ):
                print("WARN: Access totals mismatch. Retrying dedicated Access extraction before response...")
                try:
                    from pdf_extractor import extract_transactions as _et
                    retry_results = await asyncio.to_thread(_et, stored_path, bank_identifier="access")
                    retry_candidates = [
                        rs for rs in retry_results
                        if rs.get("transactions")
                    ]
                    if retry_candidates:
                        retry_stmt = max(retry_candidates, key=lambda rs: len(rs.get("transactions", [])))
                        retry_txns = retry_stmt.get("transactions", [])
                        retry_meta = retry_stmt.get("metadata", {})
                        retry_validation = validate_totals(retry_txns, retry_meta)
                        if retry_validation.get("totals_match") is True:
                            print(
                                "WARN: Access retry repaired totals "
                                f"({len(txns)} -> {len(retry_txns)} transactions)."
                            )
                            txns = retry_txns
                            meta = retry_meta
                            validation_result = retry_validation
                        else:
                            print(f"WARN: Access retry still failed: {retry_validation.get('status')}")
                except Exception as e:
                    print(f"WARN: Access retry failed: {e}")

            # Step 2b: FAIL-FAST check for generic retry
            if txns and not meta.get("_retried"):
                empty_desc_count = sum(1 for t in txns if not (t.get('description') or t.get('remarks') or '').strip())
                empty_pct = empty_desc_count / len(txns)
                detected_bank = meta.get('bank', 'generic')

                if empty_pct > 0.25 and detected_bank not in ['gtbank', 'providus', 'zenith', 'access', 'uba', 'fcmb', 'keystone', 'wema', 'sterling', 'moniepoint', 'opay'] and file_ext == '.pdf':
                    print(f'WARN: {empty_pct:.0%} empty descriptions. Retrying statement with generic mapping...')
                    from pdf_extractor import extract_transactions as _et
                    retry_results = await asyncio.to_thread(_et, stored_path, bank_identifier='generic')
                    # Find matching account in retry results
                    for rs in retry_results:
                         if rs['metadata'].get('account_no') == meta.get('account_no'):
                              txns = rs['transactions']
                              meta = rs['metadata']
                              meta["_retried"] = True
                              validation_result = validate_totals(txns, meta)
                              break
            
            # Step 3: Categorize (rules + AI fallback)
            categorization_started = time.perf_counter()
            categorized_txns = categorize_transactions(txns)
            print(
                "INFO [ANALYZE-TIMING] "
                f"categorization={time.perf_counter() - categorization_started:.2f}s "
                f"transactions={len(txns)}"
            )
            
            processed_statements.append({
                "transactions": categorized_txns,
                "metadata": meta,
                "validation": validation_result
            })

        # Step 4: Generate Excel (Pass all statements)
        excel_started = time.perf_counter()
        generate_excel(processed_statements, {}, excel_path)
        print(f"INFO [ANALYZE-TIMING] excel={time.perf_counter() - excel_started:.2f}s")

        # Build combined summary based on ALL statements
        total_debit = 0.0
        total_credit = 0.0
        total_txns = 0
        
        for s in processed_statements:
            total_debit += sum(num(t.get("debit")) for t in s["transactions"])
            total_credit += sum(num(t.get("credit")) for t in s["transactions"])
            total_txns += len(s["transactions"])

        # Prefer the statement that actually has transactions for top-level display.
        # Some merged PDFs contain cover/empty account sections as group[0].
        primary_stmt = None
        if processed_statements:
            non_empty = [s for s in processed_statements if s.get("transactions")]
            primary_stmt = max(non_empty, key=lambda s: len(s.get("transactions", []))) if non_empty else processed_statements[0]

        primary_meta = primary_stmt["metadata"] if primary_stmt else {}
        primary_validation = primary_stmt["validation"] if primary_stmt else {}
        statement_debit_total = sum(num(s["metadata"].get("statement_total_debit")) for s in processed_statements)
        statement_credit_total = sum(num(s["metadata"].get("statement_total_credit")) for s in processed_statements)
        all_have_statement_totals = bool(processed_statements) and all(
            s["metadata"].get("statement_total_debit") is not None and
            s["metadata"].get("statement_total_credit") is not None
            for s in processed_statements
        )
        display_total_debit = statement_debit_total if all_have_statement_totals else total_debit
        display_total_credit = statement_credit_total if all_have_statement_totals else total_credit

        # Robust period handling
        period = primary_meta.get("statement_period") or "N/A"

        # Absolute download URL
        download_url = str(request.base_url).rstrip("/") + f"/download/{file_id}"

        summary = {
            "accountName": primary_meta.get("account_name", "Detected Organization"),
            "period": period,
            "totalDebit": display_total_debit,
            "totalCredit": display_total_credit,
            "extractedTotalDebit": total_debit,
            "extractedTotalCredit": total_credit,
            "statementTotalDebit": primary_meta.get("statement_total_debit"),
            "statementTotalCredit": primary_meta.get("statement_total_credit"),
            "openingBalance": primary_meta.get("opening_balance"),
            "closingBalance": primary_meta.get("closing_balance"),
            "transactionCount": total_txns,
            "validationStatus": primary_validation.get("status", "Unknown"),
            "totalsMatch": primary_validation.get("totals_match", None),
            "bank": primary_meta.get("bank") or normalized_bank,
            "multiStatement": len(processed_statements) > 1,
            "statementCount": len(processed_statements)
        }

        # Return a combined preview so the frontend doesn't show 0 when first group is empty.
        preview_txns = []
        for s in processed_statements:
            preview_txns.extend(s.get("transactions", []))
        
        # Step 5: Deep Audit Summary (Optional / Move to background)
        audit_summary = "Audit in progress... refresh in 30 seconds."
        # if os.getenv("ANTHROPIC_API_KEY") and processed_statements:
        #     all_txns = []
        #     for s in processed_statements:
        #         all_txns.extend(s["transactions"])
        #     audit_summary = generate_audit_summary(all_txns, {
        #         **primary_meta,
        #         "total_debits": total_debit,
        #         "total_credits": total_credit
        #     })

        response_payload = {
            "file_id": file_id, 
            "backend_version": "v2.1-STABLE-FINAL-CORP-V10",
            "summary": {
                **summary,
                "auditSummary": audit_summary
            }, 
            "downloadUrl": download_url,
            "transactions": preview_txns
        }
        print(
            "INFO [ANALYZE-TIMING] "
            f"total={time.perf_counter() - request_started:.2f}s "
            f"detected_bank={summary['bank']} transactions={total_txns}"
        )
        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in /analyze ({file_id}): {error_details}")
        if os.getenv("DEBUG_ERRORS", "false").lower() == "true":
            detail = f"Analysis failed: {str(e)}\n\nFull error:\n{error_details}"
        else:
            detail = f"Analysis failed. Please retry or contact support with reference {file_id}."
        raise HTTPException(status_code=500, detail=detail)

    finally:
        # Clean up temp upload file after processing
        try:
            if stored_path.exists():
                stored_path.unlink()
        except Exception:
            pass

@app.get("/download/{file_id}")
async def download_excel(file_id: str):
    """
    Download endpoint for generated Excel file
    """
    cleanup_stale_temp_files()
    if not UUID_RE.fullmatch(file_id):
        raise HTTPException(status_code=404, detail="File not found")

    excel_path = DOWNLOAD_DIR / f"statement-analysis-{file_id}.xlsx"
    
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=excel_path,
        filename=f"statement-analysis.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.post("/classify-analysis")
async def classify_analysis(payload: AIClassifyRequest):
    """
    AI fallback classifier for already-extracted transaction rows.
    Secrets must be provided as environment variables; no API keys are accepted
    from the browser or stored in frontend code.
    """
    if len(payload.transactions) > MAX_CLASSIFY_TRANSACTIONS:
        raise HTTPException(status_code=413, detail="Too many transactions in one classification request")
    if len(payload.customInstructions or "") > MAX_CLASSIFY_INSTRUCTIONS_CHARS:
        raise HTTPException(status_code=400, detail="Custom instructions are too long")
    if not payload.transactions:
        return {"results": []}

    template = payload.template or {}
    categories = [
        {
            "name": c.get("name"),
            "outputLabel": c.get("outputLabel"),
            "description": c.get("description"),
            "appliesTo": c.get("appliesTo"),
        }
        for c in template.get("categories", [])
    ]
    allowed_categories = {
        str(c.get("outputLabel") or c.get("name") or "").strip()
        for c in categories
        if str(c.get("outputLabel") or c.get("name") or "").strip()
    }
    allowed_categories.update({"Review Required", "Out of Scope"})
    instructions = payload.customInstructions or template.get("aiInstructions") or ""
    rows = [t.model_dump() for t in payload.transactions[:50]]

    prompt = f"""
Classify ONLY the provided bank transaction rows. Do not invent rows, amounts, dates, balances or totals.
Return strict JSON only in this structure:
{{"results":[{{"id":"transaction id","category":"string","subCategory":null,"taxAuthority":"FIRS/SIRS/Not Applicable/Review Required/null","confidence":"High/Medium/Low","reason":"short explanation","reviewRequired":true}}]}}

Template:
{json.dumps({"name": template.get("name"), "scope": template.get("scope"), "categories": categories}, ensure_ascii=False)}

Instructions:
{instructions}

Rows:
{json.dumps(rows, ensure_ascii=False)}
"""

    def _fallback_results():
        return {
            "results": [
                {
                    "id": row["id"],
                    "category": "Review Required",
                    "subCategory": None,
                    "taxAuthority": "Review Required" if template.get("id") == "firs-sirs-na" else None,
                    "confidence": "Low",
                    "reason": "No deterministic rule matched and AI provider is unavailable.",
                    "reviewRequired": True,
                    "decisionSource": "SYSTEM",
                }
                for row in rows
            ]
        }

    try:
        if os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You classify existing bank transaction rows and return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
        elif os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model=os.getenv("ANTHROPIC_CLASSIFIER_MODEL", "claude-3-haiku-20240307"),
                max_tokens=3000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text if response.content else "{}"
            data = json.loads(content)
        else:
            return _fallback_results()

        results = data.get("results", [])
        if not isinstance(results, list):
            return _fallback_results()
        valid_ids = {row["id"] for row in rows}
        cleaned = []
        for item in results:
            if item.get("id") not in valid_ids:
                continue
            category = str(item.get("category") or "").strip()
            category_is_allowed = category in allowed_categories
            cleaned.append({
                "id": item.get("id"),
                "category": category if category_is_allowed else "Review Required",
                "subCategory": item.get("subCategory"),
                "taxAuthority": item.get("taxAuthority"),
                "confidence": item.get("confidence") if item.get("confidence") in ["High", "Medium", "Low"] else "Low",
                "reason": item.get("reason") if category_is_allowed else "AI returned a category outside the selected template.",
                "reviewRequired": bool(item.get("reviewRequired") or item.get("confidence") == "Low" or not category_is_allowed),
                "decisionSource": "AI",
            })
        return {"results": cleaned}
    except Exception as e:
        print(f"WARN: AI analysis classifier failed: {e}")
        return _fallback_results()


def clean_narrative_response(data: Dict[str, Any], allowed_ids: set, fallback_summary: str) -> Dict[str, Any]:
    findings = []
    for item in data.get("findings", [])[:8]:
        evidence_ids = [
            str(value) for value in item.get("evidenceTransactionIds", [])[:25]
            if str(value) in allowed_ids
        ]
        findings.append({
            "title": str(item.get("title") or "Analysis finding")[:120],
            "body": str(item.get("body") or "")[:800],
            "severity": item.get("severity") if item.get("severity") in {"Positive", "Neutral", "Review"} else "Neutral",
            "evidenceTransactionIds": evidence_ids,
        })
    return {
        "generatedBy": "AI",
        "summary": str(data.get("summary") or fallback_summary or "")[:1200],
        "findings": findings,
        "caveats": [str(value)[:500] for value in data.get("caveats", [])[:8]],
    }


@app.post("/analysis-narrative")
async def analysis_narrative(payload: AINarrativeRequest):
    """Render verified deterministic metrics into a cited narrative."""
    request_data = payload.model_dump()
    if len(json.dumps(request_data, ensure_ascii=False)) > MAX_NARRATIVE_PAYLOAD_CHARS:
        raise HTTPException(status_code=413, detail="Narrative input is too large")

    allowed_ids = {str(value) for value in payload.allowedEvidenceIds[:250] if str(value).strip()}
    prompt = f"""
Write a concise bank-statement analysis using ONLY the verified facts below.
Do not calculate new totals, invent transactions, identify fraud, or provide legal/tax conclusions.
Every finding must cite only transaction IDs from allowedEvidenceIds.
Return strict JSON only:
{{"summary":"string","findings":[{{"title":"string","body":"string","severity":"Positive/Neutral/Review","evidenceTransactionIds":["id"]}}],"caveats":["string"]}}

Verified insights:
{json.dumps(payload.insights, ensure_ascii=False)}

Quality gate:
{json.dumps(payload.quality, ensure_ascii=False)}

Deterministic narrative:
{json.dumps(payload.deterministicNarrative, ensure_ascii=False)}

allowedEvidenceIds:
{json.dumps(sorted(allowed_ids), ensure_ascii=False)}
"""

    try:
        if os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_NARRATIVE_MODEL", os.getenv("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini")),
                messages=[
                    {"role": "system", "content": "You summarize verified financial metrics and cite only supplied transaction IDs."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            data = json.loads(response.choices[0].message.content or "{}")
        elif os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model=os.getenv("ANTHROPIC_NARRATIVE_MODEL", os.getenv("ANTHROPIC_CLASSIFIER_MODEL", "claude-3-haiku-20240307")),
                max_tokens=1800,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(response.content[0].text if response.content else "{}")
        else:
            raise HTTPException(status_code=503, detail="AI narrative provider is not configured")

        return clean_narrative_response(
            data,
            allowed_ids,
            str(payload.deterministicNarrative.get("summary") or ""),
        )
    except HTTPException:
        raise
    except Exception as exc:
        print(f"WARN: AI narrative generation failed: {exc}")
        raise HTTPException(status_code=503, detail="AI narrative generation is unavailable")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    Catch-all route to serve React SPA (index.html)
    Exclude API routes (start with /analyze, /download, /docs, /openapi.json)
    """
    if full_path.startswith(("api", "convert", "analyze", "download", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="API route not found")
        
    # Serve index.html for all other routes
    if DIST_DIR.exists():
        index_path = DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
    
    return {"message": "Backend running. Frontend not found (dev mode or missing build)."}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*40}")
    print(f"!!! STARTING BACKEND v2.3-ULTRA-STABLE !!!")
    print(f"!!! Listening on port: {port} (IPv4) !!!")
    print(f"!!! Timeout Support: 1800s Proxy Sync !!!")
    print(f"{'='*40}\n")
    # Increased timeout to 600s for idle keep-alive support
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=600)
