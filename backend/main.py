from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import uuid
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

from pdf_extractor import extract_transactions
from excel_extractor import extract_excel_transactions
from validation import validate_totals
from categorization import categorize_transactions
from excel_generator import generate_excel
from claude_service import generate_audit_summary

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Backend is reachable"}

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("temp_uploads")
DOWNLOAD_DIR = Path("temp_downloads")
UPLOAD_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

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

def num(x):
    """Safely convert to float, handling strings with commas"""
    try:
        return float(str(x).replace(",", ""))
    except:
        return 0.0

@app.post("/analyze")
async def analyze_statement(
    request: Request,
    file: UploadFile = File(...),
    bank: str = Form("auto")  # auto, gtbank, accessbank, firstbank, zenith, uba, etc.
):
    print(f"\n{'!'*40}")
    print(f"!!! [ANALYZE-FORENSIC] Request received: {file.filename} (Bank: {bank}) !!!")
    print(f"{'!'*40}\n")
    
    # Audit file size
    try:
        content = await file.read()
        await file.seek(0) # Reset for later use
        print(f"  [FORENSIC] Upload Buffer Size: {len(content)} bytes")
    except Exception as e:
        print(f"  [FORENSIC] Error reading buffer: {e}")
    """
    Main endpoint: accepts PDF, returns summary + download URL
    
    Parameters:
    - file: PDF bank statement
    - bank: Optional bank identifier (auto, gtbank, accessbank, firstbank, zenith, uba)
           Defaults to 'auto' for automatic detection
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in [".pdf", ".xlsx", ".xls", ".csv"]:
        raise HTTPException(status_code=400, detail="Only PDF, Excel (.xlsx, .xls), and CSV files are supported")

    file_id = str(uuid.uuid4())
    stored_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    excel_path = DOWNLOAD_DIR / f"statement-analysis-{file_id}.xlsx"

    success = False
    try:
        content = await file.read()
        stored_path.write_bytes(content)

        # Step 1: Extract transactions (Non-blocking background thread)
        import asyncio
        if file_ext == ".pdf":
            statement_results = await asyncio.to_thread(extract_transactions, stored_path, bank_identifier=bank.lower())
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

            # Step 2b: FAIL-FAST check for generic retry
            if txns and not meta.get("_retried"):
                empty_desc_count = sum(1 for t in txns if not (t.get('description') or t.get('remarks') or '').strip())
                empty_pct = empty_desc_count / len(txns)
                detected_bank = meta.get('bank', 'generic')

                if empty_pct > 0.25 and detected_bank not in ['gtbank', 'providus', 'zenith', 'access', 'uba', 'fcmb', 'wema', 'sterling'] and file_ext == '.pdf':
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
            categorized_txns = categorize_transactions(txns)
            
            processed_statements.append({
                "transactions": categorized_txns,
                "metadata": meta,
                "validation": validation_result
            })

        # Step 4: Generate Excel (Pass all statements)
        generate_excel(processed_statements, {}, excel_path)

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

        # Robust period handling
        period = primary_meta.get("statement_period") or "N/A"

        # Absolute download URL
        download_url = str(request.base_url).rstrip("/") + f"/download/{file_id}"

        summary = {
            "accountName": primary_meta.get("account_name", "Detected Organization"),
            "period": period,
            "totalDebit": total_debit,
            "totalCredit": total_credit,
            "transactionCount": total_txns,
            "validationStatus": primary_validation.get("status", "Unknown"),
            "totalsMatch": primary_validation.get("totals_match", None),
            "bank": bank.lower(),
            "multiStatement": len(processed_statements) > 1,
            "statementCount": len(processed_statements)
        }

        success = True
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

        return {
            "file_id": file_id, 
            "backend_version": "v2.1-STABLE-FINAL-CORP-V6",
            "summary": {
                **summary,
                "auditSummary": audit_summary
            }, 
            "downloadUrl": download_url,
            "transactions": preview_txns
        }

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in /analyze: {error_details}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}\n\nFull error:\n{error_details}")

    finally:
        # Clean up temp upload file after processing
        try:
            if success and stored_path.exists():
                stored_path.unlink()
        except Exception:
            pass

@app.get("/download/{file_id}")
async def download_excel(file_id: str):
    """
    Download endpoint for generated Excel file
    """
    excel_path = DOWNLOAD_DIR / f"statement-analysis-{file_id}.xlsx"
    
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=excel_path,
        filename=f"statement-analysis.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    Catch-all route to serve React SPA (index.html)
    Exclude API routes (start with /analyze, /download, /docs, /openapi.json)
    """
    if full_path.startswith("api") or full_path.startswith("analyze") or full_path.startswith("download"):
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
