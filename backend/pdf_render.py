"""
PDF Page Rendering Helper using PyMuPDF

Simple utility to render PDF pages to PNG images
"""
import fitz  # pymupdf


def render_page_png(pdf_path: str, page_index: int, zoom: float = 2.0) -> bytes:
    """
    Render a PDF page to PNG bytes.
    
    Args:
        pdf_path: Path to PDF file
        page_index: Zero-based page index
        zoom: Zoom factor (2.0 = 144 DPI, 3.0 = 216 DPI)
    
    Returns:
        PNG image as bytes
    """
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes
