import re
from collections import defaultdict


# ============================================================
# EXTRACT GIST FROM SUMMARY TEXT
# ============================================================

def extract_gist(summary_text):

    match = re.search(
        r'Gist of amendment:\s*(.*?)(?=Existing provisions of Law prior to amendment:|Action point for listed entity if any:|$)',
        summary_text,
        flags=re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return ""


# ============================================================
# EXTRACT ACTION POINT FROM SUMMARY TEXT
# ============================================================

def extract_action(summary_text):

    match = re.search(
        r'Action point for listed entity if any:\s*(.*?)$',
        summary_text,
        flags=re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return ""


# ============================================================
# COMBINE ALL FOOTNOTE SUMMARIES INTO ONE MASTER SUMMARY
# ============================================================

def generate_master_summary(mapped_data):

    title          = str(mapped_data.get("Title", "")).strip()
    effective_date = str(mapped_data.get("effective_date", "")).strip()
    sub_category   = str(mapped_data.get("SubCategory", "")).strip()
    footnotes      = mapped_data.get("mapped_footnotes", {})

    # # ----------------------------------------------------------
    # # Opening verb from title
    # # ----------------------------------------------------------

    # title_lower = title.lower()

    # if "amendment" in title_lower:
    #     opening_verb = "amended"
    # elif "insertion" in title_lower:
    #     opening_verb = "introduced"
    # else:
    #     opening_verb = "amended"
    # ----------------------------------------------------------
    # Determine amendment actions from footnotes
    # ----------------------------------------------------------

    actions = set()

    for payload in footnotes.values():

        footer_text = str(
            payload.get("footer_text", "")
        ).lower()

        if "inserted" in footer_text:
            actions.add("inserted")

        if "substituted" in footer_text:
            actions.add("substituted")

        if "omitted" in footer_text:
            actions.add("omitted")

    action_text = ", ".join(
        sorted(actions)
    )
    # ----------------------------------------------------------
    # Short regulation name
    # ----------------------------------------------------------

    reg_name_match = re.search(
        r"Securities and Exchange Board of India\s*\((.+?)\)\s*(Amendment\s*)?Regulations",
        title,
        flags=re.IGNORECASE,
    )

    reg_short = reg_name_match.group(1).strip() if reg_name_match else title

    # ----------------------------------------------------------
    # Header
    # ----------------------------------------------------------

    lines = []

    # lines.append(
    #     f"The SEBI has {opening_verb} the Securities and Exchange Board of India "
    #     f"({reg_short}) Regulations."
    # )
    lines.append(
        f"The SEBI has issued the Securities and Exchange Board of India "
        f"({reg_short}) Regulations and has {action_text} various provisions."
    )
    
    lines.append("")

    if sub_category:
        lines.append(f"Sub domain: {sub_category}")
        lines.append("")

    if effective_date:
        lines.append(f"Effective date: {effective_date}")
        lines.append("")

    # ----------------------------------------------------------
    # Process footnotes in numeric order
    # ----------------------------------------------------------

    sorted_ids = sorted(
        footnotes.keys(),
        key=lambda x: int(x) if x.isdigit() else 0
    )

    all_action_points = []

    for fid in sorted_ids:

        payload      = footnotes[fid]
        summary_text = payload.get("summary", "").strip()
        footer_text  = payload.get("footer_text", "").strip()
        chunks       = payload.get("mapped_regulation_chunks", [])

        if not summary_text:
            continue

        # Regulation number from first chunk's section field
        reg_no = ""
        if chunks:
            reg_no = str(chunks[0].get("section", "")).strip()

        gist   = extract_gist(summary_text)
        action = extract_action(summary_text)

        if not gist:
            continue

        lines.append(f"Regulation Number: {reg_no or 'Not provided'}")
        lines.append(f"Footer Number: {fid}")
        lines.append(f"Gist of amendment: {gist}")
        lines.append(f"Existing provisions of Law prior to amendment: {footer_text}")
        lines.append("")

        if action:
            all_action_points.append(action)

    # ----------------------------------------------------------
    # All action points at the end
    # ----------------------------------------------------------

    if all_action_points:
        lines.append("Action point for listed entity if any:")
        for ap in all_action_points:
            lines.append(f"  - {ap}")

    return "\n".join(lines)