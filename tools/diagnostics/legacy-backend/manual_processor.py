import pdfplumber
import pandas as pd
import re

def clean_currency(value):
    """Converts string currency (e.g. '1,200.50') to float."""
    if not value: return 0.0
    # Remove commas, handle () as negative, strip whitespace
    clean_str = str(value).replace(",", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

def is_money(value):
    """Checks if a string looks like a number (for column detection)."""
    if not value: return True # Empty strings in numeric cols are common
    clean = str(value).replace(",", "").replace(".", "").replace("-", "").strip()
    return clean.isdigit()

def process_zenith_merged(pdf_path, csv_output_path):
    print(f"Processing: {pdf_path}...")
    
    all_rows = []
    
    # 1. Extract Raw Data
    with pdfplumber.open(pdf_path) as pdf:
        # Verification Totals
        text = pdf.pages[0].extract_text()
        deb_match = re.search(r"Total Debit:[\s\S]*?([\d,]+\.\d{2})", text)
        cred_match = re.search(r"Total Credit:[\s\S]*?([\d,]+\.\d{2})", text)
        
        target_debit = clean_currency(deb_match.group(1)) if deb_match else 0.0
        target_credit = clean_currency(cred_match.group(1)) if cred_match else 0.0
        
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Basic cleanup: remove None, strip whitespace
                    clean_row = [cell.strip() if cell else "" for cell in row]
                    all_rows.append(clean_row)

    # 2. Smart Row Processing
    processed_data = []
    
    for row in all_rows:
        # Skip empty rows
        if not any(row): continue
        
        # Detect Header
        row_str = "".join(row).upper()
        if "DATE" in row_str and "BALANCE" in row_str:
            continue # Skip header row
            
        # We need rows that start with a Date (DD/MM/YYYY)
        # Zenith date is usually first column
        if not re.match(r"\d{2}/\d{2}/\d{4}", row[0]):
            continue

        # --- THE FIX: MERGE SPLIT DESCRIPTION ---
        # A standard Zenith row usually has:
        # [Date, Value Date, ...DESCRIPTION PARTS..., Debit, Credit, Balance]
        
        # We assume:
        # - First 2 columns are Dates.
        # - Last 3 columns are Financials (Debit, Credit, Balance).
        # - EVERYTHING in the middle is Description.
        
        # Safety check: Ensure we have enough columns
        if len(row) >= 5:
            date_posted = row[0]
            # value_date = row[1] # Not strictly needed for CSV math, but good to have
            
            # Identify the Financial Block (Last 3 columns)
            # We slice the last 3 elements
            debit_str = row[-3]
            credit_str = row[-2]
            balance_str = row[-1]
            
            # Identify the Description Block (Everything from index 2 to -3)
            # If the description was split into 2 or 3 cols, this joins them all.
            desc_parts = row[2:-3] 
            full_description = " ".join(desc_parts).strip()
            
            # Clean numbers
            debit = clean_currency(debit_str)
            credit = clean_currency(credit_str)
            balance = clean_currency(balance_str)
            
            # Balance Logic Check (Optional but recommended)
            # If Debit/Credit are swapped or ambiguous, you can enable logic here.
            # For now, we trust the column position relative to the end.
            
            processed_data.append({
                "Date": date_posted,
                "Description": full_description,
                "Debit": debit,
                "Credit": credit,
                "Balance": balance
            })

    # 3. Create DataFrame
    df = pd.DataFrame(processed_data)
    
    # 4. Verification
    calc_debit = df["Debit"].sum()
    calc_credit = df["Credit"].sum()
    
    print(f"--- Verification Report ---")
    print(f"PDF Target Debit:  {target_debit:,.2f} | CSV Debit: {calc_debit:,.2f}")
    print(f"PDF Target Credit: {target_credit:,.2f} | CSV Credit: {calc_credit:,.2f}")
    
    if abs(target_debit - calc_debit) < 1.0:
        print("✅ Debit Match")
    else:
        print("❌ Debit Mismatch (Check skipped rows)")
        
    if abs(target_credit - calc_credit) < 1.0:
        print("✅ Credit Match")
    else:
        print("❌ Credit Mismatch (Check skipped rows)")

    # 5. Save
    df.to_csv(csv_output_path, index=False)
    print(f"Saved to: {csv_output_path}")
