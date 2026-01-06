import argparse
import sys
from pathlib import Path
import fitz  # pymupdf

def direct_edit_pdf(input_path: str, search_text: str, replace_text: str, output_path: str):
    """
    Search for text in a PDF, redact it, and replace it with new text.
    
    Args:
        input_path: Path to input PDF
        search_text: Text to search for (exact match)
        replace_text: Text to insert in place
        output_path: Path to save the modified PDF
    """
    try:
        doc = fitz.open(input_path)
        print(f"Opened: {input_path}")
        
        total_replacements = 0
        
        for page_num, page in enumerate(doc):
            # 1. Search for text to get coordinates
            rects = page.search_for(search_text)
            
            if not rects:
                continue
                
            print(f"Page {page_num + 1}: Found {len(rects)} instance(s) of '{search_text}'")
            
            for rect in rects:
                # 2. Analyze original text to get font/size/color
                # We use get_text("dict") with the clip set to our found rect
                text_dict = page.get_text("dict", clip=rect)
                
                # Default values
                font_size = 11
                font_name = "helv"
                color = (0, 0, 0)
                
                # Try to extract actual values from the first matching span
                try:
                    for block in text_dict["blocks"]:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                if span["text"].strip():
                                    font_size = span["size"]
                                    font_name = span["font"]
                                    # Convert color from int/hex to RGB tuple (0-1)
                                    # PyMuPDF docs say color is sRGB integer, but insert_text expects tuple
                                    # Actually in "dict", color is an int
                                    c_int = span["color"]
                                    r = ((c_int >> 16) & 255) / 255
                                    g = ((c_int >> 8) & 255) / 255
                                    b = (c_int & 255) / 255
                                    color = (r, g, b)
                                    break
                            else: continue
                            break
                        else: continue
                        break
                except Exception as e:
                    print(f"Warning: Could not extract font info: {e}")

                print(f"  Replacing at {rect}: Font: {font_name}, Size: {font_size:.1f}, Color: {color}")

                # 3. Redact the old text
                page.add_redact_annot(rect)
                page.apply_redactions()
                
                # 4. Insert new text with matching style
                # Adjust y-position: PyMuPDF insert_text uses baseline, but rect is bbox.
                # A simple heuristic is to use the bottom-left of the rect + a small margin
                # or rely on insert_text's placement if using 'fontsize' correctly.
                # Ideally we use the 'origin' from the span, but we redacting the whole rect.
                
                # We'll use the bottom-left of the rect (rect.bl) minus a small descent adjustment
                # or just rect.bl - (size * 0.2) roughly.
                # Better: Use the 'origin' from the span if we found one? 
                # For now let's use rect.bl and rely on visual check.
                
                page.insert_text(
                    point=rect.bl, # This puts the baseline at the bottom of the rect
                    text=replace_text,
                    fontsize=font_size,
                    fontname="helv", # We can't easily map arbitrary PDF fonts to builtin ones, so safe default
                    color=color
                )
                
                total_replacements += 1
                
        if total_replacements > 0:
            doc.save(output_path)
            print(f"\nSuccess! Replaced {total_replacements} instances.")
            print(f"Saved to: {output_path}")
        else:
            print(f"\nNo instances of '{search_text}' found.")
            
    except Exception as e:
        print(f"Error: {e}")
        # import traceback
        # traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Directly edit a PDF by finding and replacing text.")
    parser.add_argument("input_pdf", help="Input PDF file path")
    parser.add_argument("search_text", help="Text to search for")
    parser.add_argument("replace_text", help="Text to replace with")
    parser.add_argument("-o", "--output", help="Output PDF file path", default="output.pdf")
    
    args = parser.parse_args()
    
    input_path = Path(args.input_pdf)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)
        
    direct_edit_pdf(str(input_path), args.search_text, args.replace_text, args.output)

if __name__ == "__main__":
    main()
