from pypdf import PdfReader
import traceback

pdf_path = 'test_fidelity.pdf.pdf'

try:
    reader = PdfReader(pdf_path)
    page = reader.pages[1] # Page 2
    
    words = []
    
    def visitor(text, cm, tm, fontDict, fontSize):
        if text.strip():
            # tm is [a, b, c, d, e, f] where e, f are x, y
            x = tm[4]
            y = tm[5]
            words.append({
                "text": text,
                "x0": x,
                "y0": y
            })
            
    print("Attempting pypdf visitor extraction...")
    page.extract_text(visitor_text=visitor)
    print(f"Extracted {len(words)} tokens successfully!")
    print("\nFirst 10 tokens:")
    for w in words[:10]:
        print(w)
except Exception:
    traceback.print_exc()
