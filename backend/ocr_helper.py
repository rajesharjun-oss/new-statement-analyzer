"""
OCR Fallback Helper for PDF Extraction using PyMuPDF

Uses OpenAI Vision API and PyMuPDF (fitz) for robust PDF image extraction
"""
import os
from pathlib import Path
import io

# Import PyMuPDF (fitz) - much more reliable than pdf2image, no poppler needed
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Try to import OpenAI Vision
try:
    from openai_vision import extract_header_with_vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    def extract_header_with_vision(*args, **kwargs):
        return ""


def pdf_page_to_png_bytes(pdf_path: str, page_num: int = 0) -> bytes:
    """
    Convert a PDF page to PNG bytes for OCR using PyMuPDF.
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
    
    Returns:
        PNG image as bytes
    """
    try:
        from pdf_render import render_page_png
        png_bytes = render_page_png(pdf_path, page_num, zoom=4.17)  # ~300 DPI (72 * 4.17 ≈ 300)
        print(f"Converted PDF page {page_num} to PNG ({len(png_bytes)} bytes)")
        return png_bytes
    except Exception as e:
        print(f"PDF rendering failed: {e}")
        raise RuntimeError(f"Could not convert PDF page {page_num} to image: {e}")


def extract_header_with_openai_vision(pdf_path: str, page_num: int = 0) -> str:
    """
    Extract table headers from a PDF page using OpenAI Vision.
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number to extract from (0-indexed)
    
    Returns:
        Extracted header text
    """
    if not VISION_AVAILABLE:
        raise ImportError("OpenAI Vision not available. Check openai_vision.py and OPENAI_API_KEY")
    
    # Convert PDF page to image using PyMuPDF
    png_bytes = pdf_page_to_png_bytes(pdf_path, page_num)
    
    # Use OpenAI Vision to extract headers
    header_text = extract_header_with_vision(png_bytes)
    
    print(f"OpenAI Vision extracted headers from page {page_num}: {header_text}")
    return header_text
