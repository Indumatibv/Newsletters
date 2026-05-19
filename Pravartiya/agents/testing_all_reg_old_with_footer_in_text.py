import pdfplumber
import re
import json


# ============================================================
# CLEAN LEGAL TEXT
# ============================================================

def clean_legal_text(text):

    # Remove standalone page numbers
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)

    # Remove excessive spaces/tabs
    text = re.sub(r'[ \t]+', ' ', text)

    # Normalize newlines
    text = re.sub(r'\n{2,}', '\n\n', text)

    return text.strip()


# ============================================================
# EXTRACT TEXT FROM PDF
# ============================================================

def extract_pdf_text(pdf_path):

    full_text = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            text = page.extract_text()

            if text:
                full_text.append(text)

    return "\n".join(full_text)


# ============================================================
# CREATE REGULATION CHUNKS
# ============================================================
def create_regulation_chunks(title, text):
    chunks = []
    text = clean_legal_text(text)

    # ========================================================
    # REMOVE INDEX / PREAMBLE
    # ========================================================
    start_match = re.search(
        r'(CHAPTER\s+[IVXLC]+|SCHEDULE\s+[IVXLC0-9\-A-Z ]+)',
        text,
        re.IGNORECASE
    )
    if start_match:
        text = text[start_match.start():]

    # ========================================================
    # CHAPTER / SCHEDULE DETECTION
    # ========================================================
    chapter_pattern = re.compile(
        r'(CHAPTER\s+[IVXLC]+)\s*\n([^\n]+)',
        re.MULTILINE
    )

    schedule_pattern = re.compile(
        r'^\s*(SCHEDULE\s+[IVXLC0-9\-A-Z ]+)'
        r'(?:\s*\n([^\n]+))?',
        re.MULTILINE
    )
    chapter_matches = []

    for m in chapter_pattern.finditer(text):
        chapter_matches.append({"match": m, "is_schedule": False})

    for m in schedule_pattern.finditer(text):
        chapter_matches.append({"match": m, "is_schedule": True})

    # Sort by position
    chapter_matches = sorted(
        chapter_matches,
        key=lambda x: x["match"].start()
    )

    if not chapter_matches:
        chapter_matches = [None]

    # ========================================================
    # PROCESS CHAPTERS / SCHEDULES
    # ========================================================
    for idx in range(len(chapter_matches)):
        if chapter_matches[idx]:
            current_match = chapter_matches[idx]["match"]
            is_schedule = chapter_matches[idx]["is_schedule"]
            ch_start = current_match.start()
            ch_end = (
                chapter_matches[idx + 1]["match"].start()
                if idx + 1 < len(chapter_matches)
                else len(text)
            )

            chapter_text = text[ch_start:ch_end]
            chapter = current_match.group(1).strip()
            chapter_title = (
                current_match.group(2).strip()
                if current_match.group(2)
                else ""
            )
        else:
            chapter_text = text
            chapter = None
            chapter_title = None
            is_schedule = False

        # ====================================================
        # REGULATION / PARAGRAPH DETECTION
        # ====================================================
        if is_schedule:
            regulation_pattern = re.compile(
                r'\n([A-Z0-9\-]+(?:\.[A-Z0-9]+)?|[IVXLC]+|PART\s+[A-Z])\.\s+(.*?)(?=\n)',
                re.MULTILINE | re.IGNORECASE
            )
        else:
            # Looks behind to capture the heading line sitting directly ABOVE the regulation number
            regulation_pattern = re.compile(
                r'(?:(?<=\n)([^\n]+)\n)?^(\d+[A-Z\-]*)\.\s+',
                re.MULTILINE
            )

        regulation_matches = []
        for m in regulation_pattern.finditer(chapter_text):
            if is_schedule:
                regulation_matches.append({
                    "start": m.start(),
                    "section": m.group(1).strip(),
                    "inferred_heading": m.group(2).strip()
                })
            else:
                raw_heading = m.group(1).strip() if m.group(1) else ""
                
                # Filter out standard noise lines from acting as section headers
                if any(x in raw_heading.lower() for x in ["chapter", "schedule", "provided that", "page"]):
                    raw_heading = ""

                regulation_matches.append({
                    "start": m.start(),
                    "section": m.group(2).strip(),
                    "inferred_heading": raw_heading
                })

        if is_schedule and not regulation_matches:
            # Clean fallback block text and replace all structural newlines with space breaks
            clean_fallback_text = re.sub(
                r'\n\s*\d+\s+(?:Inserted|Substituted|Omitted|Amended|Prior|Modified|w\.e\.f\.).*', 
                '', 
                chapter_text, 
                flags=re.IGNORECASE
            )
            clean_fallback_text = re.sub(r'\s*\n\s*', ' ', clean_fallback_text).strip()
            
            chunks.append({
                "title": title,
                "chapter": chapter,
                "chapter_title": chapter_title,
                "section": "FULL",
                "section_heading": chapter_title,
                "footer_reference": [],
                "text": clean_fallback_text
            })
            continue

        # ====================================================
        # PROCESS REGULATIONS / SECTIONS
        # ====================================================
        for r_idx in range(len(regulation_matches)):
            r_start = regulation_matches[r_idx]["start"]
            r_end = (
                regulation_matches[r_idx + 1]["start"]
                if r_idx + 1 < len(regulation_matches)
                else len(chapter_text)
            )

            regulation_block = chapter_text[r_start:r_end].strip()
            section = regulation_matches[r_idx]["section"]
            regulation_heading = regulation_matches[r_idx]["inferred_heading"].strip()

            # =================================================
            # EXTRACT FOOTNOTE REFERENCE NUMBERS
            # =================================================
            footer_refs = re.findall(r'\b(\d+)(?=\[)', regulation_block)
            footer_refs = sorted(list(set([int(x) for x in footer_refs])))

            # =================================================
            # SURGICALLY REMOVE FOOTNOTE DEFINITIONS
            # =================================================
            clean_block = re.sub(
                r'\n\s*\d+\s+(?:Inserted|Substituted|Omitted|Amended|Prior|Modified|w\.e\.f\.).*',
                '',
                regulation_block,
                flags=re.IGNORECASE
            )

            # =================================================
            # ISOLATE AND CLEAN TEXT BODY
            # =================================================
            regulation_text = clean_block.strip()
            
            # If heading was matched out up top, peel it out from body boundary text cleanly
            if regulation_heading and regulation_text.startswith(regulation_heading):
                regulation_text = regulation_text[len(regulation_heading):].strip()

            # Remove section number prefix (e.g. "2.") from start of text body safely
            if regulation_text.startswith(section):
                prefix_len = len(section) + 1
                regulation_text = regulation_text[prefix_len:].strip()

            # -------------------------------------------------
            # CRITICAL CLEANUP: WIPE OUT ALL TRAILING \n ENTRIES
            # -------------------------------------------------
            # Flattens any remaining mid-line or trailing newlines into standard spacing breaks
            regulation_text = re.sub(r'\s*\n\s*', ' ', regulation_text)
            regulation_text = re.sub(r'[ \t]+', ' ', regulation_text).strip()
            
            regulation_heading = re.sub(r'\s*\n\s*', ' ', regulation_heading)
            regulation_heading = re.sub(r'[ \t]+', ' ', regulation_heading).strip()

            # Safety fallback for heading context mapping
            if not regulation_heading:
                regulation_heading = regulation_text[:60] + "..." if len(regulation_text) > 60 else regulation_text

            # =================================================
            # STORE CHUNK
            # =================================================
            chunks.append({
                "title": title,
                "chapter": chapter,
                "chapter_title": chapter_title,
                "section": section,
                "section_heading": regulation_heading,
                "footer_reference": footer_refs,
                "text": regulation_text
            })

    return chunks
# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    PDF_PATH = "/Users/admin/Downloads/1777351317428.pdf"

    TITLE = (
        "SEBI Listing Obligations and "
        "Disclosure Requirements Regulations"
    )

    # --------------------------------------------------------
    # Extract text from PDF
    # --------------------------------------------------------

    text = extract_pdf_text(PDF_PATH)

    # --------------------------------------------------------
    # Create chunks
    # --------------------------------------------------------

    chunks = create_regulation_chunks(
        title=TITLE,
        text=text
    )

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    with open(
        "regulation_chunks.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            chunks,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(f"Created {len(chunks)} chunks")