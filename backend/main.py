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

app = FastAPI()

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
# Only mount if dist exists (production mode)
DIST_DIR = Path("/app/dist")
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

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

        # Step 1: Extract transactions
        if file_ext == ".pdf":
            transactions, metadata = extract_transactions(stored_path, bank_identifier=bank.lower())
        else:
            # Excel/CSV handling
            transactions, metadata = extract_excel_transactions(stored_path)

        # Step 2: Validate totals
        validation_result = validate_totals(transactions, metadata)

        # Step 2b: FAIL-FAST check — if >25% of descriptions empty and bank is not GTBank,
        # retry extraction with generic keyword mapping before proceeding.
        if transactions:
            empty_desc_count = sum(
                1 for t in transactions
                if not (t.get('description') or t.get('remarks') or '').strip()
            )
            empty_pct = empty_desc_count / len(transactions)
            detected_bank = metadata.get('bank', 'generic')

            if empty_pct > 0.25 and detected_bank not in ['gtbank', 'providus', 'zenith', 'access', 'uba', 'fcmb', 'wema', 'sterling'] and file_ext == '.pdf':
                print(f'WARN: {empty_pct:.0%} empty descriptions for bank={detected_bank}. Retrying with generic mapping...')
                from pdf_extractor import extract_transactions as _et
                retry_txns, retry_meta = _et(stored_path, bank_identifier='generic')
                retry_empty = sum(
                    1 for t in retry_txns
                    if not (t.get('description') or t.get('remarks') or '').strip()
                )
                if retry_txns and retry_empty < empty_desc_count:
                    print(f'INFO: Generic retry improved descriptions. Using retry results.')
                    transactions = retry_txns
                    metadata = retry_meta
                    validation_result = validate_totals(transactions, metadata)

        # Step 3: Categorize (rules + AI fallback)
        categorized_transactions = categorize_transactions(transactions)

        # Step 4: Generate Excel
        generate_excel(categorized_transactions, validation_result, excel_path)

        # Build summary with numeric safety
        total_debit = sum(num(t.get("debit")) for t in categorized_transactions)
        total_credit = sum(num(t.get("credit")) for t in categorized_transactions)

        # Robust period handling
        dates = [t.get("date") for t in categorized_transactions if t.get("date")]
        period = metadata.get("statement_period") or (f"{dates[0]} to {dates[-1]}" if dates else "N/A")

        # Absolute download URL
        download_url = str(request.base_url).rstrip("/") + f"/download/{file_id}"

        summary = {
            "accountName": metadata.get("account_name", "Detected Organization"),
            "period": period,
            "totalDebit": total_debit,
            "totalCredit": total_credit,
            "transactionCount": len(categorized_transactions),
            "validationStatus": validation_result.get("status", "Unknown"),
            "totalsMatch": validation_result.get("totals_match", None),
            "statementTotalDebit": validation_result.get("statement_total_debit", None),
            "statementTotalCredit": validation_result.get("statement_total_credit", None),
            "extractedTotalDebit": validation_result.get("extracted_total_debit", None),
            "extractedTotalCredit": validation_result.get("extracted_total_credit", None),
            "debit_diff": validation_result.get("debit_diff", None),
            "credit_diff": validation_result.get("credit_diff", None),
            "bank": bank.lower()
        }

        success = True
        return {
            "file_id": file_id, 
            "summary": summary, 
            "downloadUrl": download_url,
            "transactions": categorized_transactions
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
