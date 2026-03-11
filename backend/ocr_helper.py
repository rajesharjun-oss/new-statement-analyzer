"""
OCR Fallback Helper for PDF Extraction
Supports specific OCR engines via OCR_ENGINE env var (openai | tesseract)
"""
import os
import fitz  # PyMuPDF
import io
from PIL import Image

# Import Tesseract if available
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    
    # Configure Tesseract Path (Critical for Windows)
    # 1. Check env var TESSERACT_CMD
    # 2. Check common Windows paths if on Windows
    tess_path = os.getenv("TESSERACT_CMD")
    if tess_path:
        pytesseract.pytesseract.tesseract_cmd = tess_path
    elif os.name == 'nt':
        # Default fallback for this specific user/environment
        default_path = r"C:\Users\ionawoga\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default_path):
             pytesseract.pytesseract.tesseract_cmd = default_path
        else:
             # Try Program Files as last resort
             pf_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
             if os.path.exists(pf_path):
                 pytesseract.pytesseract.tesseract_cmd = pf_path

except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None

# Import OpenAI Vision if available
try:
    from openai_vision import extract_header_with_vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    def extract_header_with_vision(*args, **kwargs):
        return ""

# Import Gemini Vision if available
try:
    from standard_ocr import extract_text_with_gemini_vision
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    def extract_text_with_gemini_vision(*args, **kwargs):
        return ""

def render_page_to_bytes(pdf_path: str, page_num: int = 0, zoom: float = 2.0) -> bytes:
    """Read specific page from PDF and convert to PNG bytes using PyMuPDF"""
    try:
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            return b""
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
    except Exception as e:
        print(f"PDF Render Failed: {e}")
        return b""

def extract_text_with_ocr(pdf_path: str, page_num: int = 0) -> str:
    """
    Main entry point for OCR.
    Dispatches to the configured engine in .env (OCR_ENGINE)
    """
    engine = os.getenv("OCR_ENGINE", "openai").lower().strip()
    
    print(f"DEBUG: Using OCR_ENGINE={engine}")
    
    if engine == "openai":
        return extract_header_with_openai_vision(pdf_path, page_num)
        
    elif engine == "gemini":
        return extract_text_with_gemini(pdf_path, page_num)
        
    elif engine == "tesseract":
        return extract_text_with_tesseract(pdf_path, page_num)
        
    else:
        raise ValueError(f"Invalid OCR_ENGINE value: '{engine}'. Must be 'openai', 'gemini' or 'tesseract'.")

def extract_header_with_openai_vision(pdf_path: str, page_num: int = 0) -> str:
    """OpenAI Vision implementation"""
    if not VISION_AVAILABLE:
        raise ImportError("OpenAI Vision module not available.")
    
    if not os.getenv("OPENAI_API_KEY"):
         raise ValueError("OCR_ENGINE=openai but OPENAI_API_KEY is missing.")

    png_bytes = render_page_to_bytes(pdf_path, page_num, zoom=3.0)
    if not png_bytes:
        return ""
        
    return extract_header_with_vision(png_bytes)


def extract_text_with_tesseract(pdf_path: str, page_num: int = 0) -> str:
    """Tesseract implementation"""
    if not TESSERACT_AVAILABLE:
        raise ImportError("pytesseract is not installed. Please install it (pip install pytesseract) and Tesseract binary.")
        
    png_bytes = render_page_to_bytes(pdf_path, page_num, zoom=3.0)
    if not png_bytes:
        return ""
        
    # Convert bytes to PIL Image
    image = Image.open(io.BytesIO(png_bytes))
    
    # Run Tesseract
    # assume basic English
    text = pytesseract.image_to_string(image)
    print(f"DEBUG: Tesseract extracted {len(text)} chars")
    return text

def extract_text_with_gemini(pdf_path: str, page_num: int = 0) -> str:
    """Gemini Implementation"""
    if not GEMINI_AVAILABLE:
        raise ImportError("Gemini Vision module not available.")
    
    if not os.getenv("GEMINI_API_KEY"):
         raise ValueError("OCR_ENGINE=gemini but GEMINI_API_KEY is missing.")

    png_bytes = render_page_to_bytes(pdf_path, page_num, zoom=3.0)
    if not png_bytes:
        return ""
        
    return extract_text_with_gemini_vision(png_bytes)
