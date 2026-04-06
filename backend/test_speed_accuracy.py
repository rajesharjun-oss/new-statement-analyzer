import os
import time
import glob
from pathlib import Path
from pdf_extractor import extract_transactions
from main import num, validate_totals
from claude_service import generate_audit_summary

def test_performance():
    # Find up to 3 pdfs prioritizing standard test files
    target_dir = Path.cwd()
    pdf_files = [
        target_dir / "temp_uploads" / "Access2.0.pdf",
        target_dir / "UBA test.pdf",
        target_dir / "Adam Providus.pdf",
        target_dir / "GTCO test 2.pdf",
        target_dir / "WEMA test.pdf"
    ]
    
    test_files = [f for f in pdf_files if f.exists()][:3]
    
    if not test_files:
        print("No test PDFs found!")
        return
        
    print(f"Testing {len(test_files)} bank statements...\n")
    
    for pdf_path in test_files:
        print("="*50)
        print(f"Testing: {pdf_path.name}")
        start_time = time.time()
        
        try:
            # 1. Extraction
            extract_start = time.time()
            statement_results = extract_transactions(str(pdf_path), bank_identifier='auto')
            extract_end = time.time()
            
            # Combine transactions correctly (assuming statement_results is a list of dicts)
            all_txns = []
            primary_meta = statement_results[0]['metadata'] if statement_results else {}
            
            for s in statement_results:
                all_txns.extend(s.get('transactions', []))
                
            # Combine totals
            total_debit = sum(num(t.get('debit', 0)) for t in all_txns)
            total_credit = sum(num(t.get('credit', 0)) for t in all_txns)
            
            valid_stats = validate_totals(all_txns, {
                **primary_meta,
                "total_debits": total_debit,
                "total_credits": total_credit
            })
            
            # 2. Categorization & Audit
            audit_start = time.time()
            audit_summary = None
            if os.getenv("ANTHROPIC_API_KEY") and statement_results:
                audit_summary = generate_audit_summary(all_txns, {
                    **primary_meta,
                    "total_debits": total_debit,
                    "total_credits": total_credit
                })
            audit_end = time.time()
            
            total_time = audit_end - start_time
            
            print(f"Bank: {primary_meta.get('bank', 'Unknown')}")
            print(f"Account: {primary_meta.get('account_name', 'Unknown')}")
            print(f"Transactions Extracted: {len(all_txns)}")
            print(f"Match Status: {valid_stats.get('status')} | Totals Match: {valid_stats.get('totals_match')}")
            
            print("\n--- TIMINGS ---")
            print(f"Extraction & Routing: {extract_end - extract_start:.2f} seconds")
            print(f"Deep Audit (Claude): {audit_end - audit_start:.2f} seconds")
            print(f"TOTAL TIME: {total_time:.2f} seconds")
            
            print("\n--- AUDIT SUMMARY PREVIEW ---")
            print(audit_summary[:300] + "...\n" if audit_summary else "N/A\n")
            
        except Exception as e:
            print(f"ERROR processing {pdf_path.name}: {e}")

if __name__ == "__main__":
    test_performance()
