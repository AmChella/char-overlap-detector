#!/usr/bin/env python3
"""
Diagnostic script to test if coordinates are being drawn correctly.
Creates a simple marked PDF with coordinate labels.
"""

import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color

def create_diagnostic_pdf(input_pdf, output_pdf):
    """Create a test PDF with coordinate markers at known positions."""
    reader = PdfReader(open(input_pdf, "rb"))
    writer = PdfWriter()
    
    page = reader.pages[0]  # First page only
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    print(f"Page dimensions: {page_width} x {page_height}")
    
    # Create overlay with test markers
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    
    # Draw reference markers at known positions
    test_positions = [
        (50, 50, "BOTTOM-LEFT (50,50)"),
        (50, page_height - 50, f"TOP-LEFT (50,{page_height-50:.0f})"),
        (page_width - 150, 50, f"BOTTOM-RIGHT ({page_width-150:.0f},50)"),
        (page_width - 150, page_height - 50, f"TOP-RIGHT ({page_width-150:.0f},{page_height-50:.0f})"),
        (page_width/2 - 50, page_height/2, f"CENTER ({page_width/2:.0f},{page_height/2:.0f})")
    ]
    
    for x, y, label in test_positions:
        # Draw a red rectangle
        c.setStrokeColor(Color(1, 0, 0, alpha=0.8))
        c.setFillColor(Color(1, 0, 0, alpha=0.3))
        c.setLineWidth(2)
        c.rect(x, y, 100, 30, fill=1, stroke=1)
        
        # Add text label
        c.setFillColor(Color(0, 0, 0))
        c.setFont("Helvetica", 8)
        c.drawString(x + 2, y + 10, label)
    
    c.save()
    buf.seek(0)
    
    # Merge overlay onto original page
    overlay_reader = PdfReader(buf)
    overlay_page = overlay_reader.pages[0]
    page.merge_page(overlay_page)
    
    writer.add_page(page)
    
    with open(output_pdf, "wb") as f_out:
        writer.write(f_out)
    
    print(f"\nCreated diagnostic PDF: {output_pdf}")
    print("\nExpected positions:")
    print("  - BOTTOM-LEFT box should be in the bottom-left corner")
    print("  - TOP-LEFT box should be in the top-left corner")  
    print("  - CENTER box should be in the center of the page")
    print("\nIf boxes appear in wrong positions, there's a coordinate system issue.")

if __name__ == "__main__":
    create_diagnostic_pdf("pdfs/CACE_108782.pdf", "pdfs/diagnostic_test.pdf")
