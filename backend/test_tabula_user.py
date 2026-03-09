import tabula
import pandas as pd

def extract_providus_statement(pdf_path, output_excel):
    # Extract all tables from the PDF pages
    tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)
    
    if tables:
        # Combine all extracted tables into a single DataFrame
        combined_df = pd.concat(tables, ignore_index=True)
        
        # Clean up any completely empty rows or columns
        combined_df.dropna(how='all', inplace=True)
        combined_df.dropna(axis=1, how='all', inplace=True)
        
        # Export the compiled data to Excel
        combined_df.to_excel(output_excel, index=False)
        print(f"Extraction successful. Extracted {len(combined_df)} rows. File saved as: {output_excel}")
    else:
        print("No tables could be found or extracted from the PDF.")

# Run the extraction
pdf_file = "temp_uploads/Adam Providus.pdf"
excel_file = "Providus_Statement_Extracted.xlsx"

extract_providus_statement(pdf_file, excel_file)
