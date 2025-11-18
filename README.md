# PDF Glyph Overlap Detector

A tool to detect and highlight character-level overlaps in PDF files using glyph drawing coordinates extracted via Apache PDFBox.

## Features

- **Glyph-level overlap detection**: Detects overlapping characters based on actual glyph drawing coordinates (not text bounding boxes)
- **Watermark filtering**: Automatically filters out large watermark text (like "UNCORRECTED PROOF") to reduce false positives
- **Visual annotation**: Creates marked PDF copies with semi-transparent red rectangles highlighting all overlapping glyphs
- **Batch processing**: Automatically processes all PDFs in the `pdfs/` directory
- **Efficient detection**: Uses the existing `intersects()` function to check bounding box overlaps
- **Character-specific whitespace trimming**: Optional trimming of character-specific whitespace from glyph bounding boxes to reduce false positives (e.g., punctuation, brackets, thin letters)
- **Percentage-based overlap filtering**: Filter overlaps by actual geometric overlap percentage
- **Position labels**: Automatically adds region-based overlap counts on marked PDFs
- **JSON export**: Export detailed overlap data with geometric percentages
- **Configurable**: Command-line options to control watermark filtering, trimming, thresholds, and output

## Requirements

- Python 3.x
- Java (for PDFBox)
- Python packages:
  - jpype1
  - PyPDF2
  - reportlab

## Installation

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install jpype1 PyPDF2 reportlab
```

## Usage

### Basic Usage

Place your PDF files in the `pdfs/` directory and run:

```bash
# Default mode - filters out watermarks
python run.py
```

The script will:
1. Process all PDF files (skipping already-marked ones)
2. Extract glyph drawing coordinates using PDFBox
3. Filter out watermark text (font size ≥ 40pt)
4. Detect overlapping glyphs on each page
5. Create marked PDF copies (with `_marked.pdf` suffix) if overlaps are found

### Watermark Filtering

**Default behavior** (recommended):
```bash
python run.py
```
Filters out watermarks, reducing false positives:
- Removes glyphs with font size ≥ 40pt (e.g., "UNCORRECTED PROOF")
- Filters common watermark characters in 20-40pt range

**Include watermarks** (if you need to detect overlaps in watermark text):
```bash
python run.py --include-watermarks
```

**View all options**:
```bash
python run.py --help
```

### Character-Specific Whitespace Trimming

Reduce false positives by trimming character-specific whitespace from glyph bounding boxes:

```bash
# Enable character-specific trimming (default scale: 1.0)
python run.py --trim-whitespace

# Use less aggressive trimming (50% of default)
python run.py --trim-whitespace --trim-scale 0.5

# Use more aggressive trimming (200% of default)
python run.py --trim-whitespace --trim-scale 2.0
```

**Trimming categories** (with default percentages per side at scale=1.0):
- Small punctuation (`,`, `.`, `;`, `:`, `'`, `"`): 25% horizontal, 20% vertical
- Thin stems (`i`, `l`, `|`, `1`, `t`): 12% horizontal, 18% vertical  
- Hooks (`f`, `j`): 10% horizontal, 12% vertical
- Brackets (`(`, `)`, `[`, `]`, `{`, `}`): 8-10%
- Diacritics (`~`, `^`): 20%
- Letters: 7% horizontal, 10% vertical
- Digits: 6% horizontal, 8% vertical

**Example impact** (CACE_108782.pdf with watermark filtering):
- Without trimming: **111 overlaps**
- With trimming (`--trim-whitespace`): **17 overlaps** (85% reduction in false positives)

### Overlap Percentage Filtering

Filter overlaps by actual geometric overlap percentage:

```bash
# Only mark overlaps where >10% of the union area overlaps
python run.py --union-threshold 10

# Only mark severe overlaps (>20% union percentage)
python run.py --union-threshold 20

# Combine with trimming for best results
python run.py --trim-whitespace --union-threshold 10
```

### JSON Export

Export detailed overlap data with geometric percentages:

```bash
# Export overlap data to JSON
python run.py --json

# JSON output includes:
# - overlap_area: intersection area in square points
# - percentage_of_char_a: % of character A covered by overlap
# - percentage_of_char_b: % of character B covered by overlap  
# - percentage_of_union: % of combined area (union) that overlaps
```

### Overlap Count Threshold

Only create marked PDFs if total overlaps exceed a threshold:

```bash
# Only mark PDFs with more than 50 overlaps
python run.py --threshold 50
```

### Position Labels

Disable automatic position labels on marked PDFs:

```bash
# No position labels (cleaner output)
python run.py --no-labels
```

### Output Examples

**With watermark filtering (default):**
```
Processing 1 PDF(s)... (watermark filtering: enabled)

Processing: CACE_108782.pdf...   (Filtered 224 watermark glyphs) ✓ 111 overlaps | marked: CACE_108782_marked.pdf
```

**With whitespace trimming:**
```
Processing: CACE_108782.pdf...   (Filtered 224 watermark glyphs)   (Trimmed 43332 glyph boxes) ✓ 17 overlaps | marked: CACE_108782_marked.pdf
```

**Without watermark filtering:**
```
Processing 1 PDF(s)... (watermark filtering: disabled)

Processing: CACE_108782.pdf... ✓ 1503 overlaps | marked: CACE_108782_marked.pdf
```

### Marked PDFs

For each PDF with overlaps, a new file is created with:
- Original filename + `_marked.pdf` suffix
- Semi-transparent red rectangles around all overlapping glyphs
- Optional position labels showing overlap counts by region (9 positions: top/middle/bottom × left/center/right)
- All original content preserved

## How It Works

1. **Glyph Extraction**: Uses `GlyphExtractor.java` (via PDFBox) to extract precise glyph drawing coordinates:
   - Character text
   - Page number (1-based)
   - Bounding box: x, y, width, height
   - Font size (for watermark detection)

2. **Watermark Filtering** (optional, enabled by default):
   - Filters glyphs with font size ≥ 40pt (typical watermarks like "UNCORRECTED PROOF")
   - Filters single letters in 20-40pt range that match common watermark patterns
   - Significantly reduces false positives from diagonal watermark text

3. **Character-Specific Trimming** (optional):
   - Trims character-specific whitespace from glyph bounding boxes
   - Different trim percentages for different character categories
   - Reduces false positives from punctuation, brackets, and thin letters
   - Configurable via `--trim-whitespace` and `--trim-scale` flags

4. **Overlap Detection**: 
   - Groups glyphs by page
   - Checks every pair of glyphs on the same page using bounding box intersection
   - Calculates actual geometric overlap percentages (area, char A %, char B %, union %)
   - Filters by union percentage threshold if specified
   - Collects all glyphs involved in overlaps

5. **Position Analysis**:
   - Categorizes overlaps by page region (9 positions: top/middle/bottom × left/center/right)
   - Generates character statistics showing most frequent overlapping characters
   - Adds position labels to marked PDFs (unless disabled)

6. **PDF Annotation**:
   - Creates overlay with semi-transparent red rectangles using top-left coordinate system
   - Adds position labels showing overlap counts by region
   - Uses reportlab to draw annotations
   - Merges overlay with original PDF using PyPDF2

7. **JSON Export** (optional):
   - Exports detailed overlap data with geometric percentages
   - Includes character positions and overlap metrics for each overlap pair

## Files

- `run.py` - Main script for processing PDFs
- `finder.py` - PDFBox wrapper to extract glyph coordinates
- `GlyphExtractor.java` - Java class that extends PDFBox's PDFTextStripper
- `pdfs/` - Directory containing input PDFs and marked output files
- `lib/` - Apache PDFBox JAR files

## Example Statistics

For a typical academic paper with "UNCORRECTED PROOF" watermarks (14 pages, ~44,000 glyphs):

**Default (watermark filtering only):**
- Processing time: ~10-15 seconds
- Watermark glyphs filtered: ~224
- Overlaps detected: **111 overlaps**
- Output file size: Similar to input (6-7 MB)

**With character-specific trimming (recommended):**
- Watermark glyphs filtered: ~224
- Glyph boxes trimmed: ~43,332
- Overlaps detected: **17 overlaps** (85% reduction from default)
- Most overlaps are mathematical symbols (⎪, |, ˜, brackets)

**With union percentage threshold (10%):**
- Overlaps marked: **21 overlaps** (filtered 295/316)

**With union percentage threshold (20%):**  
- Overlaps marked: **13 overlaps** (filtered 303/316)

**Without watermark filtering:**
- Overlaps detected: ~1,500 (includes ~1,400 false positives from watermarks)

## Technical Notes

- **Coordinate System**: Uses PDFBox's coordinate system (bottom-left origin)
- **Page Numbers**: 1-based indexing to match PDFBox
- **Transparency**: Red boxes use 30% alpha for visibility without obscuring text
- **Performance**: O(n²) overlap checks per page (standard approach for pairwise comparison)

## Suppressing Java Warnings

PDFBox may emit warnings about font issues. To suppress them:

```bash
python run.py 2>/dev/null
```

## Backup

The original `run.py` is backed up as `run.py.bak` before modifications.
