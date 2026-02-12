import pdfplumber

pdf_path = "test_fidelity.pdf.pdf"

try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total pages: {len(pdf.pages)}")
        
        for i in range(min(3, len(pdf.pages))):
            print(f"\n=== PAGE {i} ===")
            page = pdf.pages[i]
            
            # Try extracting words
            print("Extracting words...")
            words = page.extract_words(x_tolerance=2, y_tolerance=2, use_text_flow=True)
            print(f"Words extracted: {len(words)}")
            
            if words:
                print(f"First 5 words:")
                for w in words[:5]:
                    print(f"  {w.get('text','N/A')} at x0={w.get('x0','N/A')}")
                    
            print("SUCCESS!")
            
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
