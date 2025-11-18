import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.TextPosition;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDType3Font;
import org.apache.pdfbox.pdmodel.font.PDVectorFont;

import java.awt.Shape;
import java.awt.geom.AffineTransform;
import java.awt.geom.Rectangle2D;
import java.awt.geom.GeneralPath;

public class GlyphExtractor extends PDFTextStripper {

    public static class Glyph {
        public String ch;
        public int page;
        public double x, y, w, h;
    }

    public List<Glyph> glyphs = new ArrayList<>();

    public GlyphExtractor() throws IOException {
        super();
    }

    @Override
    protected void processTextPosition(TextPosition text) {
        try {
            PDFont font = text.getFont();

            // Correct API for PDFBox 2.0.35
            int code = text.getCharacterCodes()[0];

            // In PDFBox 2.0.x, only PDVectorFont and PDType3Font support getPath()
            GeneralPath path = null;
            if (font instanceof PDVectorFont) {
                path = ((PDVectorFont) font).getPath(code);
            } else if (font instanceof PDType3Font) {
                path = ((PDType3Font) font).getPath(text.getUnicode());
            }
            
            if (path == null) {
                // Fallback: use text position bounding box directly
                Glyph g = new Glyph();
                g.ch = text.getUnicode();
                g.page = getCurrentPageNo();
                g.x = text.getX();
                g.y = text.getY();
                g.w = text.getWidth();
                g.h = text.getHeight();
                glyphs.add(g);
                return;
            }

            AffineTransform at = text.getTextMatrix().createAffineTransform();
            Shape transformed = at.createTransformedShape(path);

            Rectangle2D box = transformed.getBounds2D();

            Glyph g = new Glyph();
            g.ch = text.getUnicode();
            g.page = getCurrentPageNo();
            g.x = box.getX();
            g.y = box.getY();
            g.w = box.getWidth();
            g.h = box.getHeight();

            glyphs.add(g);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    public static List<Glyph> extract(PDDocument doc) throws IOException {
        GlyphExtractor ge = new GlyphExtractor();
        ge.setSortByPosition(true);
        ge.setStartPage(1);
        ge.setEndPage(doc.getNumberOfPages());
        ge.getText(doc);
        return ge.glyphs;
    }
}
