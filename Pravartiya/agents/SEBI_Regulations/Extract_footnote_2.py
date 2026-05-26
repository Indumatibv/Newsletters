import pdfplumber
import re

# ============================================================
# EXTRACT ALL FOOTNOTES PAGE-BY-PAGE
# ============================================================
def extract_all_footers_by_page(pdf_path):
    footer_dict = {}

    # This pattern isolates a footnote starting with a number and legal keyword.
    # By running it page-by-page, \Z correctly marks the absolute bottom of the current page.
    footnote_pattern = re.compile(
        r'\n\s*(\d+)\s+((?:Inserted|Substituted|Omitted|Amended|Prior|Modified|w\.e\.f\.).*?)(?=\n\s*\d+\s+(?:Inserted|Substituted|Omitted|Amended|Prior|Modified|w\.e\.f\.)|\n\n|\Z)',
        re.DOTALL | re.IGNORECASE
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text()
            if not page_text:
                continue

            # Find all footnotes located strictly on this individual page
            for m in footnote_pattern.finditer(page_text):
                footnote_num = m.group(1).strip()
                footnote_text = m.group(2).strip()

                # Clean up formatting, tabs, and flatten broken line breaks inside the footnote
                clean_text = re.sub(r'\s*\n\s*', ' ', footnote_text)
                clean_text = re.sub(r'[ \t]+', ' ', clean_text).strip()

                # If a footnote spans multiple lines at the bottom of the SAME page, 
                # or if a key repeats, handle it gracefully
                if footnote_num in footer_dict:
                    # Append if it's unique text, avoiding duplicates
                    if clean_text not in footer_dict[footnote_num]:
                        footer_dict[footnote_num] += " " + clean_text
                else:
                    footer_dict[footnote_num] = clean_text

    return footer_dict

# ============================================================
# REUSABLE FOOTNOTE PROCESSOR
# ============================================================

def process_regulation_footnotes(
    pdf_path
):

    footnotes = extract_all_footers_by_page(
        pdf_path
    )

    return footnotes

# ============================================================
# MAIN EXECUTION
# ============================================================
# if __name__ == "__main__":
#     PDF_PATH = "/Users/admin/Downloads/1777351317428.pdf"
#     OUTPUT_JSON_PATH = "all_footers.json"

#     print("Extracting footnotes page-by-page to prevent cross-page bleeding...")
#     all_footers = extract_all_footers_by_page(PDF_PATH)

#     # Save to a dedicated JSON file
#     with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
#         json.dump(all_footers, f, indent=4, ensure_ascii=False)

#     print(f"Extraction complete! Captured {len(all_footers)} total footnotes in '{OUTPUT_JSON_PATH}'.")