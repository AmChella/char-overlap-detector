import jpype
import jpype.imports
from jpype.types import *

def start_pdfbox():
    if jpype.isJVMStarted():
        return
        
    cp = [
        ".",  # Current directory for GlyphExtractor.class
        "lib/fontbox-2.0.35.jar",
        "lib/pdfbox-2.0.35.jar",
        "lib/pdfbox-app-2.0.35.jar"
    ]

    jpype.startJVM(classpath=cp)


def extract_glyph_bboxes(pdf_path):
    start_pdfbox()
    
    # Import Java classes after JVM is started
    import java.io
    import org.apache.pdfbox.pdmodel
    import org.apache.pdfbox.text
    
    File = java.io.File
    PDDocument = org.apache.pdfbox.pdmodel.PDDocument
    PDFTextStripper = org.apache.pdfbox.text.PDFTextStripper
    
    # Compile and load custom Java class
    GlyphExtractor = jpype.JClass("GlyphExtractor")
    
    # load PDF
    doc = PDDocument.load(File(pdf_path))
    extractor = GlyphExtractor()
    extractor.setSortByPosition(True)
    extractor.setStartPage(1)
    extractor.setEndPage(doc.getNumberOfPages())

    extractor.getText(doc)
    doc.close()

    # Extract glyphs from Java object
    glyphs = []
    java_list = extractor.getGlyphs()
    for i in range(java_list.size()):
        glyph_map = java_list.get(i)
        glyphs.append({
            "char": str(glyph_map.get("char")),
            "page": int(glyph_map.get("page")),
            "bbox": (
                float(glyph_map.get("x")),
                float(glyph_map.get("y")),
                float(glyph_map.get("width")),
                float(glyph_map.get("height"))
            ),
            "fontSize": float(glyph_map.get("fontSize"))
        })
    
    return glyphs
