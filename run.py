import os
import glob
import io
import argparse
import json
from typing import Dict, List, Tuple

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color

from finder import extract_glyph_bboxes


def intersects(a, b):
    """Check if two bounding boxes intersect."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax+aw <= bx or bx+bw <= ax or ay+ah <= by or by+bh <= ay)


def calculate_overlap_percentage(a, b):
    """Calculate the percentage of overlap between two bounding boxes.
    
    Returns:
        dict with:
        - overlap_area: intersection area
        - percentage_of_a: what % of box A is overlapped
        - percentage_of_b: what % of box B is overlapped
        - percentage_of_total: overlap as % of combined area
    """
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    
    # Calculate intersection rectangle
    x_left = max(ax, bx)
    y_bottom = max(ay, by)
    x_right = min(ax + aw, bx + bw)
    y_top = min(ay + ah, by + bh)
    
    if x_right < x_left or y_top < y_bottom:
        # No intersection
        return {
            "overlap_area": 0.0,
            "percentage_of_a": 0.0,
            "percentage_of_b": 0.0,
            "percentage_of_total": 0.0
        }
    
    # Calculate areas
    overlap_area = (x_right - x_left) * (y_top - y_bottom)
    area_a = aw * ah
    area_b = bw * bh
    total_area = area_a + area_b - overlap_area  # Union area
    
    return {
        "overlap_area": round(overlap_area, 2),
        "percentage_of_a": round((overlap_area / area_a * 100) if area_a > 0 else 0, 2),
        "percentage_of_b": round((overlap_area / area_b * 100) if area_b > 0 else 0, 2),
        "percentage_of_total": round((overlap_area / total_area * 100) if total_area > 0 else 0, 2)
    }


def is_watermark(glyph, watermark_font_size=40, watermark_patterns=None):
    """
    Check if a glyph is likely part of a watermark.
    
    Args:
        glyph: Glyph dict with 'char' and 'fontSize' keys
        watermark_font_size: Font size threshold for watermarks (default: 40pt)
        watermark_patterns: List of watermark text patterns to filter (default: common watermarks)
    """
    if watermark_patterns is None:
        watermark_patterns = [
            'UNCORRECTED', 'CORRECTED', 'PROOF', 'DRAFT', 
            'CONFIDENTIAL', 'PRELIMINARY', 'WATERMARK'
        ]
    
    # Filter by large font size
    if glyph.get('fontSize', 0) >= watermark_font_size:
        return True
    
    # Filter by watermark character patterns (single letters from diagonal text)
    char = glyph['char']
    if glyph.get('fontSize', 0) > 20:
        # Common watermark letters that appear individually
        watermark_chars = set('UNCORRECTEDPROFDTALIMWY')
        if len(char) == 1 and char.upper() in watermark_chars:
            return True
    
    return False


def _get_char_trim_percents(ch: str, scale: float = 1.0):
    """Return per-side trim percentages for a given character (0.0-1.0 per side)."""
    # Defaults (light trim)
    lr = 0.05 * scale
    tb = 0.05 * scale

    # Categories
    punct_small = set(list(",.;:`'\""))
    thin_stems = set(list("il|1t"))
    hooks = set(list("fj"))
    brackets = set(list("()[]{}"))
    math_ops = set(list("+-=×÷/*\\"))
    quotes = set(list("“”‘’\"'"))
    diacritics = set(list("˜^~ˇ˘¨˚˙˛˝"))  # include common diacritics and tilde

    if ch in punct_small:
        lr, tb = 0.25 * scale, 0.25 * scale
    elif ch in thin_stems:
        lr, tb = 0.12 * scale, 0.18 * scale
    elif ch in hooks:
        lr, tb = 0.10 * scale, 0.12 * scale
    elif ch in brackets or ch in quotes:
        lr, tb = 0.08 * scale, 0.10 * scale
    elif ch in math_ops:
        lr, tb = 0.10 * scale, 0.10 * scale
    elif ch in diacritics:
        lr, tb = 0.20 * scale, 0.20 * scale
    else:
        # Letters/digits default
        if ch.isdigit():
            lr, tb = 0.06 * scale, 0.08 * scale
        elif ch.isalpha():
            lr, tb = 0.07 * scale, 0.10 * scale

    # Per-side (left,right,top,bottom) all same for now; could specialize later
    return {
        'left': lr,
        'right': lr,
        'top': tb,
        'bottom': tb,
    }


def _apply_trim(bbox, percents):
    """Apply per-side percentage trim to bbox (x,y,w,h) with safety checks."""
    x, y, w, h = map(float, bbox)
    if w <= 0 or h <= 0:
        return x, y, w, h
    lt = percents.get('left', 0.0)
    rt = percents.get('right', 0.0)
    tp = percents.get('top', 0.0)
    bt = percents.get('bottom', 0.0)

    # Compute absolute trims
    dx_left = w * lt
    dx_right = w * rt
    dy_top = h * tp
    dy_bottom = h * bt

    # Apply trims (y is bottom-left origin internally)
    new_x = x + dx_left
    new_y = y + dy_bottom
    new_w = max(0.1, w - dx_left - dx_right)
    new_h = max(0.1, h - dy_top - dy_bottom)
    return new_x, new_y, new_w, new_h


def group_glyphs_by_page(glyphs_list, filter_watermarks=True, enable_char_trim=False, trim_scale=1.0):
    """
    Group glyphs by page number and optionally filter watermarks.
    Optionally apply character-specific whitespace trimming to glyph bboxes.
    Input: flat list of glyph dicts with 'page', 'bbox', 'char', and 'fontSize' keys
    Returns: dict[page_number(int starting at 1)] -> list of glyph dicts.
    """
    by_page = {}
    filtered_count = 0
    trimmed_count = 0
    
    for g in glyphs_list:
        page = g.get('page')
        if page is None:
            raise ValueError("Glyph record missing page number")
        page = int(page)
        
        # Skip watermarks if filtering enabled
        if filter_watermarks and is_watermark(g):
            filtered_count += 1
            continue
        
        # Trim bbox if enabled
        bbox = g['bbox']
        if enable_char_trim:
            perc = _get_char_trim_percents(g['char'], scale=trim_scale)
            bbox = _apply_trim(bbox, perc)
            trimmed_count += 1
        
        glyph_dict = {
            'char': g['char'],
            'x': bbox[0],
            'y': bbox[1],
            'width': bbox[2],
            'height': bbox[3]
        }
        by_page.setdefault(page, []).append(glyph_dict)
    
    if filter_watermarks and filtered_count > 0:
        print(f"  (Filtered {filtered_count} watermark glyphs)", end=" ")
    if enable_char_trim and trimmed_count > 0:
        print(f"  (Trimmed {trimmed_count} glyph boxes)", end=" ")
    
    return by_page


def find_overlaps_by_page(glyphs_by_page: Dict[int, List[dict]], overlap_percentage_threshold: float = 0.0):
    """
    Find all overlapping glyphs on each page.
    
    Args:
        glyphs_by_page: Dict of page number to list of glyph dicts
        overlap_percentage_threshold: Only include overlaps where percentage_of_union exceeds this value (0-100)
    
    Returns:
      - overlaps: list of overlap info dicts
      - highlights_by_page: dict[page] -> list of unique (x,y,w,h) tuples to highlight
      - total_overlaps: int
      - filtered_count: number of overlaps filtered out by threshold
    """
    overlaps = []
    highlights_by_page: Dict[int, List[Tuple[float,float,float,float]]] = {}
    total = 0
    filtered_count = 0

    for page_num, glyphs in glyphs_by_page.items():
        n = len(glyphs)
        page_rects = set()

        for i in range(n):
            gi = glyphs[i]
            box_i = (float(gi['x']), float(gi['y']), float(gi['width']), float(gi['height']))
            
            for j in range(i + 1, n):
                gj = glyphs[j]
                box_j = (float(gj['x']), float(gj['y']), float(gj['width']), float(gj['height']))

                if intersects(box_i, box_j):
                    # Calculate overlap percentage
                    overlap_metrics = calculate_overlap_percentage(box_i, box_j)
                    percentage_of_union = overlap_metrics['percentage_of_total']
                    
                    # Only include if exceeds threshold
                    if percentage_of_union > overlap_percentage_threshold:
                        total += 1
                        overlaps.append({
                            'page': page_num,
                            'a': box_i,
                            'b': box_j,
                            'char_a': gi['char'],
                            'char_b': gj['char'],
                            'percentage_of_union': percentage_of_union
                        })
                        page_rects.add(box_i)
                        page_rects.add(box_j)
                    else:
                        filtered_count += 1

        if page_rects:
            highlights_by_page[page_num] = list(page_rects)

    return overlaps, highlights_by_page, total, filtered_count


def get_position_label(x, y, page_width, page_height):
    """
    Get a descriptive label for the position of an overlap.
    Returns string like 'bottom-left', 'top-center', etc.
    """
    # Vertical position
    v_third = page_height / 3
    if y < v_third:
        v_pos = 'bottom'
    elif y < 2 * v_third:
        v_pos = 'middle'
    else:
        v_pos = 'top'
    
    # Horizontal position
    h_third = page_width / 3
    if x < h_third:
        h_pos = 'left'
    elif x < 2 * h_third:
        h_pos = 'center'
    else:
        h_pos = 'right'
    
    return f"{v_pos}-{h_pos}"


def annotate_pdf(input_pdf_path: str, highlights_by_page: Dict[int, List[Tuple[float,float,float,float]]], output_pdf_path: str, add_labels=True):
    """
    Create an annotated copy of the PDF with red rectangles around overlapping glyphs.
    Converts PDFBox coordinates (bottom-left origin, y increases upward) to PDF coordinates.
    
    Args:
        input_pdf_path: Path to input PDF
        highlights_by_page: Dict mapping page numbers to list of (x,y,w,h) rectangles
        output_pdf_path: Path for output PDF
        add_labels: If True, add position labels like "bottom-left" near each overlap
    """
    reader = PdfReader(open(input_pdf_path, "rb"))
    writer = PdfWriter()

    num_pages = len(reader.pages)
    for page_idx in range(num_pages):
        page_num_1_based = page_idx + 1
        page = reader.pages[page_idx]

        # Get page dimensions
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)

        # Create overlay with red rectangles
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_width, page_height))
        red = Color(1, 0, 0, alpha=0.3)  # semi-transparent red
        c.setStrokeColor(red)
        c.setFillColor(red)
        c.setLineWidth(1)

        rects = highlights_by_page.get(page_num_1_based, [])
        
        # Group overlaps by position for labeling
        position_counts = {}
        if add_labels:
            for (x, y, w, h) in rects:
                pos_label = get_position_label(x, y, page_width, page_height)
                position_counts[pos_label] = position_counts.get(pos_label, 0) + 1
        
        # Draw rectangles
        for (x, y, w, h) in rects:
            # PDFBox gives coordinates with bottom-left origin (y increases upward)
            # Convert to top-left origin: y_top = page_height - y - h
            y_topleft = page_height - y - h
            c.rect(x, y_topleft, w, h, fill=1, stroke=1)
        
        # Add position labels
        if add_labels and position_counts:
            c.setFillColor(Color(0, 0, 1, alpha=0.7))  # blue text
            c.setFont("Helvetica-Bold", 10)
            
            label_positions = {
                'bottom-left': (10, 10),
                'bottom-center': (page_width/2 - 40, 10),
                'bottom-right': (page_width - 120, 10),
                'middle-left': (10, page_height/2),
                'middle-center': (page_width/2 - 40, page_height/2),
                'middle-right': (page_width - 120, page_height/2),
                'top-left': (10, page_height - 20),
                'top-center': (page_width/2 - 40, page_height - 20),
                'top-right': (page_width - 120, page_height - 20),
            }
            
            for pos_label, count in position_counts.items():
                if pos_label in label_positions:
                    label_x, label_y = label_positions[pos_label]
                    c.drawString(label_x, label_y, f"{pos_label}: {count}")

        c.save()
        buf.seek(0)
        
        # Merge overlay onto original page
        overlay_reader = PdfReader(buf)
        overlay_page = overlay_reader.pages[0]
        
        page.merge_page(overlay_page)
        writer.add_page(page)

    # Write output PDF
    with open(output_pdf_path, "wb") as f_out:
        writer.write(f_out)


def calculate_character_statistics(overlaps: List[dict]) -> dict:
    """Calculate statistics about which characters overlap most frequently."""
    from collections import Counter
    
    char_counts = Counter()
    
    # Count each character's involvement in overlaps
    for overlap in overlaps:
        char_counts[overlap['char_a']] += 1
        char_counts[overlap['char_b']] += 1
    
    if not char_counts:
        return {"character_stats": [], "total_unique_chars": 0}
    
    # Calculate percentiles
    total_occurrences = sum(char_counts.values())
    char_stats = []
    
    for char, count in char_counts.most_common():
        percentage = (count / total_occurrences) * 100
        char_stats.append({
            "character": char,
            "overlap_count": count,
            "percentage": round(percentage, 2)
        })
    
    return {
        "character_stats": char_stats,
        "total_unique_chars": len(char_counts),
        "total_character_occurrences": total_occurrences
    }


def export_overlaps_to_json(pdf_path: str, overlaps: List[dict], total_overlaps: int, output_path: str):
    """Export overlap data to JSON file."""
    data = {
        "pdf_file": os.path.basename(pdf_path),
        "pdf_path": pdf_path,
        "total_overlaps": total_overlaps,
        "overlaps_by_page": {}
    }
    
    # Group overlaps by page
    for overlap in overlaps:
        page = overlap['page']
        if page not in data['overlaps_by_page']:
            data['overlaps_by_page'][page] = []
        
        # Calculate actual overlap percentage between the two characters
        char_a = overlap['char_a']
        char_b = overlap['char_b']
        overlap_metrics = calculate_overlap_percentage(overlap['a'], overlap['b'])
        
        overlap_entry = {
            "char_a": char_a,
            "char_b": char_b,
            "overlap_percentage": {
                "overlap_area": overlap_metrics['overlap_area'],
                "percentage_of_char_a": overlap_metrics['percentage_of_a'],
                "percentage_of_char_b": overlap_metrics['percentage_of_b'],
                "percentage_of_union": overlap_metrics['percentage_of_total']
            },
            "position_a": {
                "x": overlap['a'][0],
                "y": overlap['a'][1],
                "width": overlap['a'][2],
                "height": overlap['a'][3]
            },
            "position_b": {
                "x": overlap['b'][0],
                "y": overlap['b'][1],
                "width": overlap['b'][2],
                "height": overlap['b'][3]
            }
        }
        
        data['overlaps_by_page'][page].append(overlap_entry)
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def print_character_statistics(char_stats: dict, top_n: int = 10):
    """Print character overlap statistics to console."""
    if not char_stats['character_stats']:
        return
    
    print(f"\n  Character Overlap Statistics:")
    print(f"  ├─ Total unique characters: {char_stats['total_unique_chars']}")
    print(f"  ├─ Total character occurrences: {char_stats['total_character_occurrences']}")
    print(f"  └─ Top {min(top_n, len(char_stats['character_stats']))} most frequent:")
    
    for i, stat in enumerate(char_stats['character_stats'][:top_n], 1):
        char_display = stat['character'] if stat['character'] != ' ' else '<space>'
        bar_length = int(stat['percentage'] / 2)  # Scale for display
        bar = '█' * bar_length
        print(f"     {i:2d}. '{char_display}': {stat['overlap_count']:3d} ({stat['percentage']:5.2f}%) {bar}")


def process_pdf(pdf_path: str, filter_watermarks=True, add_labels=True, overlap_threshold=0, export_json=False, show_stats=True, union_percentage_threshold: float = 0.0, enable_char_trim=False, trim_scale=1.0):
    """Process a single PDF file for overlaps and create marked version if needed.
    
    Args:
        pdf_path: Path to PDF file
        filter_watermarks: Whether to filter watermark glyphs
        add_labels: Whether to add position labels to marked PDF
        overlap_threshold: Only create marked PDF if overlaps exceed this threshold (0 = always mark)
        export_json: Whether to export overlap data to JSON
        show_stats: Whether to print character statistics
        union_percentage_threshold: Per-overlap minimum percentage_of_union required to consider/mark (0-100)
    
    Returns:
        tuple: (total_overlaps, marked_path, json_path, char_stats, filtered_count)
    """
    # Extract glyphs using PDFBox
    glyphs_list = extract_glyph_bboxes(pdf_path)
    
    # Group by page (with optional watermark filtering and char trimming)
    glyphs_by_page = group_glyphs_by_page(glyphs_list, filter_watermarks=filter_watermarks, enable_char_trim=enable_char_trim, trim_scale=trim_scale)
    
    # Find overlaps (filtered by percentage_of_union)
    overlaps, highlights_by_page, total_overlaps, filtered_count = find_overlaps_by_page(
        glyphs_by_page, overlap_percentage_threshold=union_percentage_threshold
    )

    # Create marked PDF if overlaps exceed threshold
    marked_path = None
    if total_overlaps > overlap_threshold:
        base, ext = os.path.splitext(pdf_path)
        marked_path = f"{base}_marked{ext}"
        annotate_pdf(pdf_path, highlights_by_page, marked_path, add_labels=add_labels)
    
    # Calculate character statistics
    char_stats = calculate_character_statistics(overlaps) if total_overlaps > 0 else None
    
    # Export to JSON if requested
    json_path = None
    if export_json and total_overlaps > 0:
        base, ext = os.path.splitext(pdf_path)
        json_path = f"{base}_overlaps.json"
        export_overlaps_to_json(pdf_path, overlaps, total_overlaps, json_path)

    return total_overlaps, marked_path, json_path, char_stats, filtered_count
    return total_overlaps, marked_path


def main():
    """Main entry point - process all PDFs in pdfs/ directory."""
    parser = argparse.ArgumentParser(
        description='Detect and mark character-level overlaps in PDF files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python run.py                              # Process all PDFs with watermark filtering
  python run.py --input "file.pdf"           # Process a single PDF file
  python run.py --input "*.pdf"              # Process PDFs matching pattern
  python run.py --include-watermarks         # Include watermarks in overlap detection
  python run.py --trim-whitespace            # Trim character-specific whitespace (reduces false positives)
  python run.py --trim-whitespace --trim-scale 0.5  # Less aggressive trimming
  python run.py --json                       # Export overlap data to JSON files
  python run.py --threshold 50               # Only mark PDFs with >50 overlaps
  python run.py --union-threshold 10         # Only mark overlaps with >10% union percentage
  python run.py --union-threshold 20 --json  # Mark severe overlaps (>20% union) + export JSON
  python run.py --trim-whitespace --union-threshold 10  # Trimming + percentage filtering (recommended)
  python run.py --no-labels --json           # No position labels, with JSON export
        ''')
    
    parser.add_argument('--input', type=str, default=None, metavar='FILE_OR_PATTERN',
                        help='Input PDF file or glob pattern (e.g., "*.pdf", "file.pdf"). If not specified, processes all PDFs in pdfs/ directory')
    parser.add_argument('--include-watermarks', action='store_true',
                        help='Include watermark text in overlap detection (default: filter out watermarks)')
    parser.add_argument('--no-labels', action='store_true',
                        help='Do not add position labels (e.g., "bottom-left: 2") to marked PDFs')
    parser.add_argument('--json', action='store_true',
                        help='Export overlap data to JSON files (*_overlaps.json)')
    parser.add_argument('--threshold', type=int, default=0, metavar='N',
                        help='Only create marked PDF if overlaps exceed N (default: 0, mark all PDFs with overlaps)')
    parser.add_argument('--union-threshold', type=float, default=0.0, metavar='PCT',
                        help='Per-overlap minimum percentage_of_union required to mark/include (0-100, default: 0.0)')
    parser.add_argument('--trim-whitespace', action='store_true',
                        help='Trim character-specific whitespace from glyph bounding boxes before overlap detection')
    parser.add_argument('--trim-scale', type=float, default=1.0, metavar='SCALE',
                        help='Scale factor for whitespace trimming (default: 1.0, use 0.5 for less trim, 2.0 for more)')
    
    args = parser.parse_args()
    filter_watermarks = not args.include_watermarks
    add_labels = not args.no_labels
    export_json = args.json
    overlap_threshold = args.threshold
    union_percentage_threshold = float(args.union_threshold)
    enable_char_trim = args.trim_whitespace
    trim_scale = float(args.trim_scale)
    
    # Determine input files
    if args.input:
        # User specified a file or pattern
        if '*' in args.input or '?' in args.input:
            # It's a glob pattern
            all_pdf_paths = sorted(glob.glob(args.input))
        else:
            # It's a single file
            if os.path.isfile(args.input):
                all_pdf_paths = [args.input]
            else:
                print(f"Error: File not found: {args.input}")
                return
    else:
        # Default: process all PDFs in pdfs/ directory
        pdf_dir = os.path.join(os.path.dirname(__file__), "pdfs")
        all_pdf_paths = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    
    # Skip already-marked PDFs
    pdf_paths = [p for p in all_pdf_paths if not p.endswith('_marked.pdf')]
    
    if not pdf_paths:
        print("No PDFs found in pdfs/ directory.")
        return

    watermark_status = "disabled" if filter_watermarks else "enabled"
    threshold_msg = f" | threshold: >{overlap_threshold}" if overlap_threshold > 0 else ""
    union_pct_msg = f" | union-threshold: >{union_percentage_threshold}%" if union_percentage_threshold > 0 else ""
    json_msg = " | JSON export: on" if export_json else ""
    print(f"Processing {len(pdf_paths)} PDF(s)... (watermark filtering: {watermark_status}{threshold_msg}{union_pct_msg}{json_msg})\n")
    
    total_marked = 0
    total_json = 0
    
    for pdf_path in pdf_paths:
        pdf_name = os.path.basename(pdf_path)
        print(f"Processing: {pdf_name}...", end=" ", flush=True)
        
        try:
            overlaps_count, marked_path, json_path, char_stats, filtered_count = process_pdf(
                pdf_path, 
                filter_watermarks=filter_watermarks, 
                add_labels=add_labels,
                overlap_threshold=overlap_threshold,
                export_json=export_json,
                show_stats=True,
                union_percentage_threshold=union_percentage_threshold,
                enable_char_trim=enable_char_trim,
                trim_scale=trim_scale
            )
            
            outputs = []
            if overlaps_count == 0:
                print(f"✓ No overlaps found")
            else:
                if marked_path:
                    outputs.append(f"marked: {os.path.basename(marked_path)}")
                    total_marked += 1
                else:
                    outputs.append(f"not marked (threshold: {overlaps_count}<={overlap_threshold})")
                
                if json_path:
                    outputs.append(f"JSON: {os.path.basename(json_path)}")
                    total_json += 1
                
                if outputs:
                    print(f"✓ {overlaps_count} overlaps | {' | '.join(outputs)}")
                else:
                    print(f"✓ {overlaps_count} overlaps")
                
                # Report filtered overlaps by union threshold
                if union_percentage_threshold > 0 and filtered_count:
                    print(f"    (Filtered {filtered_count} overlaps below union threshold {union_percentage_threshold}%)")
                
                # Print character statistics
                if char_stats:
                    print_character_statistics(char_stats, top_n=10)
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    # Summary
    if len(pdf_paths) > 1:
        print(f"\n" + "="*70)
        print(f"Summary: {len(pdf_paths)} PDF(s) processed")
        if total_marked > 0:
            print(f"  • {total_marked} marked PDF(s) created")
        if total_json > 0:
            print(f"  • {total_json} JSON file(s) exported")
        print("="*70)


if __name__ == "__main__":
    main()
