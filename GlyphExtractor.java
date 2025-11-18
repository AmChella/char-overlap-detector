import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.TextPosition;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.io.IOException;

public class GlyphExtractor extends PDFTextStripper {
    private List<Map<String, Object>> glyphs;
    
    public GlyphExtractor() throws IOException {
        super();
        this.glyphs = new ArrayList<>();
    }
    
    @Override
    protected void processTextPosition(TextPosition text) {
        try {
            // getX() returns left edge of bounding box
            float x = text.getX();
            // getY() returns the text baseline, but we need the bottom of the bounding box
            // For bottom-left origin: y_bottom = y_baseline - descent
            float y = text.getY() - text.getHeightDir();
            float width = text.getWidth();
            float height = text.getHeight();
            String unicode = text.getUnicode();
            float fontSize = text.getFontSizeInPt();
            
            Map<String, Object> glyphData = new HashMap<>();
            glyphData.put("char", unicode);
            glyphData.put("page", getCurrentPageNo());
            glyphData.put("x", (double)x);
            glyphData.put("y", (double)y);
            glyphData.put("width", (double)width);
            glyphData.put("height", (double)height);
            glyphData.put("fontSize", (double)fontSize);
            
            glyphs.add(glyphData);
        } catch (Exception e) {
            System.err.println("Error processing text position: " + e.getMessage());
        }
    }
    
    public List<Map<String, Object>> getGlyphs() {
        return glyphs;
    }
}
