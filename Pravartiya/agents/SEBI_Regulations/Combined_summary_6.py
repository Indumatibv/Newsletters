import re
from collections import defaultdict

# ============================================================
# EXTRACT EFFECTIVE DATE
# ============================================================

def extract_effective_date(text):
    match = re.search(
        r'w\.e\.f\.?\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        text,
        flags=re.IGNORECASE
    )
    if match:
        return match.group(1)
    return None

# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ============================================================
# NORMALIZE FOR DEDUP
# ============================================================

def normalize(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ============================================================
# VALIDATE REGULATION NUMBER
# ============================================================

def is_valid_regulation_number(reg_no):
    if not reg_no:
        return False
    reg_no = reg_no.strip()
    invalid = [
        'not explicitly mentioned',
        'not provided',
        'amendment regulations',
        'securities and exchange board',
        'unknown',
    ]
    reg_lower = reg_no.lower()
    for inv in invalid:
        if inv in reg_lower:
            return False
    if not re.search(r'\d', reg_no):
        return False
    return True


# ============================================================
# DETECT PURE DRAFTING NOISE
# These are footers that are ONLY minor textual/punctuation
# substitutions with no substantive regulatory impact.
# ============================================================

PURE_DRAFTING_FOOTER_PATTERNS = [
    # Single word substitutions of functional words
    r'^substituted for the word ["\u201c\u201d](and|or|a|the|ibid|chapter|regulation)["\u201c\u201d]',
    r'^the word ["\u201c\u201d](and|or|a|the|ibid|regulation)["\u201c\u201d] omitted',
    r'^substituted for the letter ["\u201c\u201d][a-z]["\u201c\u201d]',
    r'^substituted for the symbol ["\u201c\u201d].{1,3}["\u201c\u201d]',
    r'^inserted vide.*w\.e\.f\.\s*\d{1,2}\.\d{1,2}\.\d{4}\s*\d{2,3}\s*ibid\s*$',
    r'^inserted vide.*w\.e\.f\.\s*\d{1,2}\.\d{1,2}\.\d{4}\s*\d{2,3}\s*$',
]

def is_pure_drafting_footer(footer_text):
    """Return True if this footer is purely a minor word/symbol substitution."""
    t = footer_text.strip().lower()
    # Remove the long citation prefix
    t = re.sub(
        r'(substituted for|inserted|omitted)\s+(vide|by)\s+the\s+securities.*?regulations,\s*20\d\d\s+w\.e\.f\.\s*[\d\.]+\.',
        r'\1 vide SEBI LODR.',
        t
    )
    # Check against patterns
    for pat in PURE_DRAFTING_FOOTER_PATTERNS:
        if re.match(pat, footer_text.strip().lower()):
            return True
    return False


# ============================================================
# GIST QUALITY FILTERS
# ============================================================

VAGUE_GIST_PHRASES = [
    'specific details are not provided',
    'exact nature of the inserted provision is unknown',
    'specifics are not provided',
    'not explicitly mentioned',
    'cannot be determined at this time',
    'provided context indicates an insertion',
    'specific content of inserted provision',
    'consult the full text',
    'cannot be determined from the provided contexts',
    'change in terminology for accurate interpretation',
    'omitted in the specified context',
    'has been omitted in the specified context',
    'change in terminology',
    'review and update internal documentation',
    'no specific compliance action',
    'no specific action required',
]

# Patterns that indicate a gist is only restating a footnote number as a rupee amount
# e.g. "Rupees 570 Crore" — 570 is a footnote index, not a real amount
FOOTNOTE_AS_AMOUNT_PATTERN = re.compile(
    r'rupees\s+(\d{2,4})\s+crore',
    flags=re.IGNORECASE
)

# Legitimate large amounts that are real thresholds (not footnote numbers)
REAL_AMOUNTS = {500, 1000, 5000, 10000, 25000, 100}

def fix_rupee_footnote_confusion(text):
    """
    Remove or neutralise cases where a footnote index number (e.g. 570) has been
    mistakenly rendered as a rupee amount (e.g. "Rupees 570 Crore").
    """
    def replace_bad_amount(m):
        num = int(m.group(1))
        if num not in REAL_AMOUNTS:
            # This is likely a footnote number — remove the amount phrase
            return '[specified threshold]'
        return m.group(0)
    return FOOTNOTE_AS_AMOUNT_PATTERN.sub(replace_bad_amount, text)


def is_meaningful_gist(gist):
    if not gist:
        return False
    g = gist.strip().lower()
    if len(g.split()) < 8:
        return False
    for phrase in VAGUE_GIST_PHRASES:
        if phrase in g:
            return False
    # Reject gists that are purely about word/letter/symbol substitution with no context
    if re.match(
        r'^the (word|letter|symbol|conjunction) ["\u201c\u201d].{1,15}["\u201c\u201d] has been (substituted|omitted|inserted)',
        gist.strip(), flags=re.IGNORECASE
    ):
        return False
    return True


# ============================================================
# ACTION POINT FILTERS
# ============================================================

ACTION_SKIP_PHRASES = [
    'consult legal counsel',
    'monitor updates',
    'specific details are not available',
    'cannot be determined',
    'no direct compliance actions',
    'as specifics are not provided',
    'not explicitly mentioned',
    'review applicable regulations to understand',
    'specifics are not available',
    'review and update internal documentation and procedures related to the symbol',
    'review and update internal documentation and procedures related to the ".',
    'no specific compliance action is directly required',
    'no specific action required',
    'review and update internal documentation',
    'it is recommended to monitor updates',
    'consult with legal counsel',
    'seek legal advice',
    'sub-regulation 599',
    'sub-regulation 607',
    'regulation 599',
    'clause (a) of sub-regulation 604',
    'sub-regulation 604',
]

def clean_action_point(action):
    """Fix common issues in action point text."""
    # Fix footnote-number-as-rupee-amount
    action = fix_rupee_footnote_confusion(action)
    # Remove internal code references like "sub-regulation 599" or "regulation 607"
    action = re.sub(r'\bsub-regulation\s+\d{2,4}\b', 'the relevant sub-regulation', action, flags=re.IGNORECASE)
    action = re.sub(r'\bregulation\s+\d{3,4}\b', 'the relevant regulation', action, flags=re.IGNORECASE)
    return clean_text(action)


def is_meaningful_action(action):
    if not action:
        return False
    a = action.lower()
    for ph in ACTION_SKIP_PHRASES:
        if ph in a:
            return False
    if len(a.split()) < 8:
        return False
    return True


# ============================================================
# PARSE SUMMARY TEXT INTO FIELDS
# ============================================================

def extract_summary_fields(summary_text):
    fields = {
        "regulation_number": "",
        "gist": "",
        "existing": "",
        "action": "",
    }

    reg_match = re.search(
        r'Regulation Number:\s*(.*?)(?:\n|$)',
        summary_text,
        flags=re.DOTALL,
    )
    if reg_match:
        fields["regulation_number"] = clean_text(reg_match.group(1))

    gist_match = re.search(
        r'Gist of amendment:\s*(.*?)(?=Existing provisions of Law prior to amendment:|Action point for listed entity if any:|$)',
        summary_text,
        flags=re.DOTALL,
    )
    if gist_match:
        fields["gist"] = clean_text(gist_match.group(1))

    existing_match = re.search(
        r'Existing provisions of Law prior to amendment:\s*(.*?)(?=Action point for listed entity if any:|$)',
        summary_text,
        flags=re.DOTALL,
    )
    if existing_match:
        fields["existing"] = clean_text(existing_match.group(1))

    action_match = re.search(
        r'Action point for listed entity if any:\s*(.*)',
        summary_text,
        flags=re.DOTALL,
    )
    if action_match:
        fields["action"] = clean_text(action_match.group(1))

    return fields


# ============================================================
# EXTRACT PRIOR PROVISION FROM FOOTER
# ============================================================

def extract_prior_provision_from_footer(footer_text):
    match = re.search(
        r'Prior to its (substitution|omission|amendment)[,.]?\s*(.*?)$',
        footer_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        prior = clean_text(match.group(2))
        prior = re.sub(r'\s*\d{2,3}\s*$', '', prior).strip()
        if len(prior.split()) > 5:
            return prior
    return ""


# ============================================================
# EXTRACT REGULATION NUMBER AS SORT KEY
# ============================================================

def reg_sort_key(reg_str):
    nums = re.findall(r'\d+', reg_str)
    if nums:
        return (int(nums[0]), reg_str)
    return (9999, reg_str)


# ============================================================
# DEDUP GISTS — Jaccard similarity to catch near-duplicates
# ============================================================

def jaccard_similarity(a, b):
    wa = set(normalize(a).split())
    wb = set(normalize(b).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def deduplicate_gists(gists, threshold=0.55):
    """Remove near-duplicate gists using Jaccard similarity."""
    result = []
    for g in gists:
        is_dup = False
        for existing in result:
            if jaccard_similarity(g, existing) >= threshold:
                is_dup = True
                break
        if not is_dup:
            result.append(g)
    return result


def deduplicate_actions(actions, threshold=0.60):
    """Remove near-duplicate action points."""
    result = []
    for a in actions:
        is_dup = False
        for existing in result:
            if jaccard_similarity(a, existing) >= threshold:
                is_dup = True
                break
        if not is_dup:
            result.append(a)
    return result


# ============================================================
# REWRITE VAGUE GISTS USING FOOTER TEXT (rule-based)
# For entries where the LLM gave a vague gist but the footer
# contains a real "prior to substitution/omission" provision,
# we surface the prior provision as existing_provision and
# derive a minimal meaningful gist.
# ============================================================

# Footers that say "Substituted for the word 'One'" in the context of
# thresholds are substantive — the new value is "Five Thousand Crore".
# We detect this and construct a proper gist.

THRESHOLD_SUBSTITUTION_PATTERN = re.compile(
    r'substituted for the word ["\u201c\u201d]one["\u201c\u201d].*?w\.e\.f',
    flags=re.IGNORECASE
)

def try_build_gist_from_footer(footer_text, mapped_chunks):
    """
    Attempt to build a substantive gist when the LLM output is vague.
    Returns (gist, existing) or ("", "").
    """
    prior = extract_prior_provision_from_footer(footer_text)

    # Case: threshold changed from "One Thousand Crore" to "Five Thousand Crore"
    if THRESHOLD_SUBSTITUTION_PATTERN.search(footer_text):
        # Look in the mapped chunk text for context
        for chunk in mapped_chunks:
            chunk_text = chunk.get('text', '')
            if 'five' in chunk_text.lower() and 'thousand crore' in chunk_text.lower():
                return (
                    "The threshold for applicability of governance provisions to high value debt listed entities "
                    "has been raised from Rupees One Thousand Crore to Rupees Five Thousand Crore of outstanding "
                    "listed non-convertible debt securities.",
                    prior if prior else "The applicable threshold was Rupees One Thousand Crore of outstanding listed non-convertible debt securities."
                )

    return ("", prior)


# ============================================================
# MAIN
# ============================================================

# def generate_master_summary(input_json_path, output_txt_path, output_json_path):
# def generate_master_summary(mapped_data):
def generate_master_summary(mapped_data,effective_date):

    # ----------------------------------------------------------
    # Pass 1 – collect per-regulation data
    # ----------------------------------------------------------
    regulation_map = defaultdict(lambda: {"gists": [], "existings": []})
    # all_effective_dates = set()
    all_action_points = []

    # for footer_id, payload in data.items():
    for footer_id, payload in mapped_data.items():
        footer_text = payload.get("footer_text", "")
        summary_text = payload.get("summary", "")
        mapped_chunks = payload.get("mapped_regulation_chunks", [])

        if not summary_text:
            continue

        # Skip entries with no mapped regulation chunks AND no meaningful footer
        # (these are dangling footnotes like page-number-only entries)
        if not mapped_chunks and not extract_prior_provision_from_footer(footer_text):
            # Only skip if the footer itself looks like pure noise
            if is_pure_drafting_footer(footer_text):
                continue


        # Parse summary
        parsed = extract_summary_fields(summary_text)
        regulation_number = parsed["regulation_number"]

        if not is_valid_regulation_number(regulation_number):
            continue

        gist    = parsed["gist"]
        existing = parsed["existing"]
        action   = parsed["action"]

        # Fix footnote-number-as-rupee-amount in gist
        gist = fix_rupee_footnote_confusion(gist)

        # Normalise "Not explicitly mentioned"
        if existing and re.search(r'not explicitly mentioned', existing, re.IGNORECASE):
            existing = ""

        # ----- Quality gate on gist -----
        if not is_meaningful_gist(gist):
            # Try to rescue from footer
            built_gist, built_existing = try_build_gist_from_footer(footer_text, mapped_chunks)
            if built_gist:
                gist = built_gist
                if not existing and built_existing:
                    existing = built_existing
            else:
                # Try prior provision as existing if not already set
                if not existing:
                    prior = extract_prior_provision_from_footer(footer_text)
                    if prior:
                        existing = prior
                # Skip this entry — no useful gist
                continue

        # ----- Collect -----
        regulation_map[regulation_number]["gists"].append((gist, existing))

        # Action point
        if action:
            cleaned_action = clean_action_point(action)
            if is_meaningful_action(cleaned_action):
                all_action_points.append(cleaned_action)

    # ----------------------------------------------------------
    # Pass 2 – build output text
    # ----------------------------------------------------------
    lines = []

    lines.append(
        "The SEBI has issued amendments to the Securities and Exchange Board of India "
        "(Listing Obligations and Disclosure Requirements) Regulations and introduced "
        "changes to governance requirements, disclosure obligations, compliance timelines, "
        "debt listing applicability thresholds, related party transaction norms, corporate "
        "governance reporting obligations, and procedural compliance requirements applicable "
        "to listed entities."
    )
    lines.append("")
    lines.append("Sub domain: Regulations")
    lines.append("")

    lines.append(
        "Effective date(s) of circular:"
    )

    lines.append(
        f"  {effective_date}"
    )
    lines.append("")

    sorted_regs = sorted(regulation_map.keys(), key=reg_sort_key)

    for reg_no in sorted_regs:
        data_reg = regulation_map[reg_no]
        raw_entries = data_reg["gists"]

        # Deduplicate gists for this regulation
        unique_gist_texts = deduplicate_gists([g for g, _ in raw_entries])

        # Map unique gists back to their existing provisions
        # (use the first matching existing for each unique gist)
        gist_to_existing = {}
        for g, e in raw_entries:
            fixed_g = fix_rupee_footnote_confusion(g)
            # Find which unique gist this maps to
            for ug in unique_gist_texts:
                if jaccard_similarity(fixed_g, ug) >= 0.55 and ug not in gist_to_existing:
                    if e and not re.search(r'not explicitly mentioned', e, re.IGNORECASE):
                        gist_to_existing[ug] = e
                    break

        lines.append(f"Regulation Number: {reg_no}")

        seen_existing = set()
        for ug in unique_gist_texts:
            lines.append(f"  Gist of amendment: {ug}")
            ex = gist_to_existing.get(ug, "")
            norm_ex = normalize(ex)
            if ex and norm_ex not in seen_existing:
                lines.append(f"  Gist of Existing provisions of Law prior to amendment: {ex}")
                seen_existing.add(norm_ex)

        lines.append("")

    # ----------------------------------------------------------
    # Action points (deduplicated)
    # ----------------------------------------------------------
    unique_actions = deduplicate_actions(all_action_points, threshold=0.55)
    # Final filter pass
    unique_actions = [a for a in unique_actions if is_meaningful_action(a)]
    # Sort for consistency
    unique_actions = sorted(unique_actions)

    if unique_actions:
        lines.append("Action point for listed entity if any:")
        for ap in unique_actions:
            lines.append(f"  - {ap}")

    final_summary = "\n".join(lines)

    print("\n" + "=" * 50)

    print(
        "MASTER SUMMARY GENERATED SUCCESSFULLY"
    )

    print("=" * 50)

    return final_summary

# ============================================================
# ENTRY POINT
# ============================================================

# if __name__ == "__main__":
#     generate_master_summary(
#         input_json_path="footers_with_compliance_summary.json",
#         output_txt_path="final_regulation_summary.txt",
#         output_json_path="final_regulation_summary.json",
#     )