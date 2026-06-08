import logging
import re
from typing import List

from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama

llm = Ollama(model="mistral:latest")


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_text(pdf_path: str) -> str:
    raw = partition_pdf(
        filename=str(pdf_path),
        strategy="fast",
        include_page_breaks=False
    )
    text = "\n".join(str(el) for el in raw if el).strip()
    if not text:
        logging.warning(
            f"Fast extraction yielded no text for {pdf_path}. Falling back to hi_res."
        )
        raw = partition_pdf(filename=str(pdf_path), strategy="hi_res")
        text = "\n".join(str(el) for el in raw if el).strip()
    return text


def extract_circular_body(text: str) -> str:
    """
    Strips annexures and legal authority paragraph so they don't
    pollute regulation extraction or LLM prompts.
    """
    m = re.search(
        r'(Annexure\s*[-]?\s*[A-Z]\b|ANNEXURE\s*[-]?\s*[A-Z]\b)',
        text,
        re.IGNORECASE,
    )
    if m:
        text = text[: m.start()].strip()

    m = re.search(
        r'This\s+Circular\s+is\s+issued\s+in\s+exercise\s+of\s+the\s+powers',
        text,
        re.IGNORECASE,
    )
    if m:
        text = text[: m.start()].strip()

    return text


# ============================================================
# DATE EXTRACTION
# ============================================================

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)


def extract_circular_date(text: str) -> str:
    header = text[:500]
    for pattern in [
        rf"((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})",
    ]:
        m = re.search(pattern, header, re.IGNORECASE)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()
    return "Not specified"


def extract_effective_date(text: str) -> str:
    """
    Extracts effective/applicability date from circular text.

    IMPORTANT: MONTHS must be wrapped in (?:...) inside capture groups.
    Without (?:...), alternation causes the capture group to return only
    the matched month name instead of the full "Month YYYY" string.

    Handles phrasings like:
    - "applicable with effect from July 01, 2026"
    - "with effect from July 1, 2026"
    - "effective from 1st July 2026"
    - "from June 2026 onwards"
    - "applicable from June 2026"
    - "come into force with immediate effect" → returns "Immediate effect"
    - "with immediate effect" → returns "Immediate effect"
    """

    if re.search(
        r'(?:come\s+into\s+force\s+with\s+immediate\s+effect'
        r'|shall\s+come\s+into\s+force\s+with\s+immediate\s+effect'
        r'|comes?\s+into\s+force\s+with\s+immediate\s+effect'
        r'|with\s+immediate\s+effect'
        r'|effective\s+immediately)',
        text,
        re.IGNORECASE,
    ):
        return "Immediate effect"
    
    # Anchor phrase covers all common variants including "applicable with effect from"
    ANCHOR = (
        r"(?:applicable\s+with\s+effect\s+from"
        r"|with\s+effect\s+from"
        r"|effective\s+from"
        r"|applicable\s+from"
        r"|w\.?e\.?f\.?\s*)"
    )
    for pattern in [
        # "... from July 01, 2026" — Month DD YYYY
        rf"{ANCHOR}\s+((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        # "... from 01 July 2026" — DD Month YYYY
        rf"{ANCHOR}\s+(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}})",
        # "... from July 2026" — Month YYYY only
        rf"{ANCHOR}\s+((?:{MONTHS})\s+\d{{4}})",
        # "from June 2026 onwards"
        rf"from\s+((?:{MONTHS})\s+\d{{4}})\s+onwards",
        # "modify/revise/implement/adopt ... from June 2026"
        # e.g. "modify MCR format from June 2026 onwards"
        rf"(?:modif(?:y|ied|ying)|revised?|implement(?:ed)?|adopt(?:ed)?)\s+(?:\w+\s+){{0,5}}from\s+((?:{MONTHS})\s+\d{{4}})",
        # Ordinal day forms: after "from" — "from 01 July, 2026"
        rf"{ANCHOR}\s+(\d{{1,2}},?\s+(?:{MONTHS}),?\s+\d{{4}})",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            # Collapse any internal whitespace/newlines from PDF extraction artifacts
            return re.sub(r'\s+', ' ', m.group(1)).strip()
    return "Not specified"

# ============================================================
# REGULATION REFERENCE EXTRACTION
# ============================================================
def extract_primary_regulation_reference(text: str) -> str:
    header = text[:1000]
    
    # Pattern 1: Compound numbered — "Regulations 44(1) and 59C of SEBI (...) Regulations, 2018"
    m = re.search(
        r"[Rr]egulations?\s+"
        r"\d+[A-Za-z]?(?:\(\d+\))*"
        r"(?:\s*,\s*\d+[A-Za-z]?(?:\(\d+\))*)*"
        r"(?:\s+and\s+\d+[A-Za-z]?(?:\(\d+\))*)?"
        r"(?:"
            r"\s+of\s+(?:SEBI\s+)?\([^)]+\)\s+Regulations(?:,?\s*\d{4})?(?:\s*\([^)]+\))?"
            r"|\s+of\s+[^\n]+?Regulations(?:,?\s*\d{4})?(?=[\s,.]|$)"
        r")?",
        header,
        re.IGNORECASE,
    )
    if m and len(m.group(0).strip()) > 10:
        return re.sub(r'\s+', ' ', m.group(0)).strip()

    # Pattern 2: Named regulation without number —
    # "SEBI (Issue of Capital and Disclosure Requirements) Regulations, 2018 ("ICDR Regulations")"
    m = re.search(
        r"SEBI\s+\([^)]+\)\s+Regulations(?:,?\s*\d{4})?(?:\s*\([^)]+\))?",
        header,
        re.IGNORECASE,
    )
    if m and len(m.group(0).strip()) > 10:
        return re.sub(r'\s+', ' ', m.group(0)).strip()

    return None

def extract_regulation_references(text: str) -> List[str]:
    # ── Step 1: try compound reference from para 1 first ──────────────────────
    primary = extract_primary_regulation_reference(text)
    if primary:
        return [primary]

    # ── Step 2: fallback — per-number regex scan ───────────────────────────────
    refs = set()
    for pattern in [
        r"[Cc]lause\s+\d+(?:\.\d+)+(?:\s+of\s+[\w\s]+(?:Circular|Regulations|Master\s+Circular))?",
        r"[Rr]egulation\s+\d+[A-Za-z]?(?:\(\d+\))*(?:\([a-zA-ZivxIVX]+\))*(?:\s+of\s+[^\n]+?Regulations(?:,?\s*\d{4})?(?=[\s,.]|$))?",
        r"[Pp]aragraph(?:s)?\s+\d+(?:\([ivxIVXa-zA-Z]+\))*(?:\s*[&,]\s*\(\w+\))*(?:\s+of\s+[\w\s]+(?:Circular|Regulations))?",
        r"[Ss]chedule\s+[IVX0-9A-Za-z]+",
        r"[Cc]hapter\s+[IVX0-9A-Za-z]+",
        r"[Ss]ection\s+\d+(?:\(\d+\))?(?:\s+of\s+[^\n]+?(?:Act|Code)(?:,?\s*\d{4})?(?=[\s,.]|$))?",
    ]:
        for match in re.finditer(pattern, text):
            refs.add(re.sub(r'\s+', ' ', match.group(0)).strip())

    # Remove Section refs
    refs = {r for r in refs if not r.lower().startswith("section")}

    # Keep only longest (most specific) version of each reference
    final_refs = []
    for ref in sorted(refs, key=len, reverse=True):
        if not any(ref.lower() in existing.lower() for existing in final_refs):
            final_refs.append(ref)

    # Priority ordering: paragraph > clause > regulation > schedule > rest
    priority_refs = []
    for ref in final_refs:
        if ref.lower().startswith("paragraph") and "circular" in ref.lower():
            priority_refs.append(ref)
    for ref in final_refs:
        if ref.lower().startswith("clause"):
            priority_refs.append(ref)
    for ref in final_refs:
        if ref.lower().startswith("regulation"):
            priority_refs.append(ref)

    paragraph_refs = [r for r in priority_refs if r.lower().startswith("paragraph")]
    if paragraph_refs:
        return paragraph_refs[:5]

    clause_refs = [r for r in priority_refs if r.lower().startswith("clause")]
    if clause_refs:
        return clause_refs[:5]

    regulation_refs = [r for r in priority_refs if r.lower().startswith("regulation")]
    if regulation_refs:
        return regulation_refs[:5]

    # Schedule refs — prefer over generic fallback
    schedule_refs = [r for r in final_refs if r.lower().startswith("schedule")]
    if schedule_refs:
        return schedule_refs[:3]

    return sorted(final_refs)
# ============================================================
# POST-PROCESSING CLEANUP
# ============================================================

ANNEXURE_SENTENCE_PATTERNS = [
    # "The revised/updated format is/has been enclosed/included/attached/provided"
    re.compile(
        r'[^.]*?(?:revised|updated|new|amended)\s+(?:\w+\s+)?format\s+'
        r'(?:is\s+|has\s+been\s+)?(?:enclosed|included|attached|provided|prescribed)[^.]*\.',
        re.IGNORECASE,
    ),
    # "format has been provided/enclosed within..."
    re.compile(
        r'[^.]*?format\s+has\s+been\s+(?:provided|enclosed|included|attached)[^.]*\.',
        re.IGNORECASE,
    ),
    # "provided/enclosed within/in this circular/document"
    re.compile(
        r'[^.]*?(?:provided|enclosed|included|attached)\s+'
        r'(?:within|in|herewith|hereto)\s+(?:this\s+)?(?:circular|document|letter)[^.]*\.',
        re.IGNORECASE,
    ),
    # "as per the enclosed/prescribed/revised [format/document]"
    # Handles multiple adjectives e.g. "as per the enclosed revised format"
    re.compile(
        r',?\s*as\s+per\s+the\s+(?:prescribed|enclosed|attached|revised|above|new)\s+'
        r'(?:(?:prescribed|enclosed|attached|revised|updated|new|above)\s+)*'
        r'(?:format|document|circular|annexure)[^.]*[.]?',
        re.IGNORECASE,
    ),
    # "enclosed/attached/included in this circular"
    re.compile(
        r'[^.]*?(?:enclosed|attached|included)\s+in\s+this\s+circular[^.]*\.',
        re.IGNORECASE,
    ),
    # Direct Annexure A/B/C references
    re.compile(
        r'[^.]*?Annexure\s+[A-Z][^.]*\.',
        re.IGNORECASE,
    ),
    # Background context: "follows the introduction / in line with the introduction /
    # pursuant to introduction / following the introduction / amendment follows"
    re.compile(
        r'[^.]*?(?:follows?\s+the\s+introduction|'
        r'in\s+line\s+with\s+the\s+introduction|'
        r'pursuant\s+to\s+(?:the\s+)?introduction|'
        r'following\s+the\s+introduction|'
        r'amendment\s+follows?)[^.]*\.',
        re.IGNORECASE,
    ),
    # "as per clause X.X of the Master Circular dated [date]" as background clause
    re.compile(
        r',\s*as\s+per\s+clause\s+[\d.]+\s+of\s+(?:the\s+)?'
        r'(?:Master\s+Circular|SEBI\s+Circular)\s+dated[^.]*\.',
        re.IGNORECASE,
    ),
]


def remove_annexure_references(text: str) -> str:
    """
    Strips sentences or clauses containing annexure references and background context.

    Also cleans up dangling decimal fragments left after partial sentence removal.
    For example, when "...as per clause 6.20 of the SEBI Master Circular..." is
    partially matched and removed, it can leave ".20 of the SEBI Master Circular..."
    which needs to be stripped separately.
    """
    for pattern in ANNEXURE_SENTENCE_PATTERNS:
        text = pattern.sub('', text)

    # Strip dangling decimal fragments: ".20 of the SEBI Master Circular dated..."
    text = re.sub(r'\.\d+\s+of\s+[^.]+\.', '.', text)

    # Strip orphaned connector fragments after a period: ". of ...", ". as per ..."
    text = re.sub(
        r'\.\s+(?:of|as|and|or|but|which|that|where|when)\s+[^.]*\.', '.', text
    )

    # Clean up extra whitespace and stray punctuation
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+\.', '.', text)
    text = text.strip()
    return text


# ============================================================
# PROMPTS
# ============================================================

GIST_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter summary
of a SEBI Circular.

Write the summary gist for this circular.

REQUIRED OPENING — start with one of the following based on what the circular does:
- "SEBI has issued this circular and introduced..."
- "SEBI has issued this circular and amended..."
- "SEBI has issued this circular and modified..."
- "SEBI has issued this circular and clarified..."

DO NOT repeat the opening phrase twice. Write it ONCE only, then continue with the content.
- WRONG: "SEBI has issued this circular and modified SEBI has introduced..."
- RIGHT: "SEBI has issued this circular and introduced a one-time relaxation..."

RULES:
- State clearly what has been changed, introduced, or clarified.
- State the NEW requirement specifically — not just that something was amended.
- Explicitly describe what regulated entities must now do.
- Avoid vague statements such as:
  "framework amended"
  "changes introduced"
  "certain provisions modified"
- State the actual new requirement, relaxation, extension, disclosure, filing, reporting or compliance obligation.
- Mention the effective date if explicitly stated in the circular.
- Include substantive new obligations (e.g. legal agreements, exceptions, conditions).
- Focus ONLY on what is NOW required — the outcome.
- PROHIBITED — do NOT include:
  * Background: do NOT mention previous circulars, dates of earlier circulars, or
    the history of how the change came about. No phrases like "originally issued on",
    "further amended on", "pursuant to", "in line with earlier circular".
  * Annexure references: "Annexure A/B", "enclosed", "attached", "prescribed format".
  * Circular index numbers or file references.
  * Email IDs or website links.
  * Phrases like "other details are specified in the circular."
  * Legal authority paragraph ("issued in exercise of powers...").
  * Vague phrases like "various changes have been made."
- HARD LIMIT: Maximum 2 sentences. Stop after the second sentence — no exceptions.
- HARD LIMIT: Maximum 80 words total.

DOCUMENT:
{text}

Return only the gist paragraph. No heading. No bullet points.
"""

ACTION_POINT_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter.

Identify the action point for the regulated entity arising from this circular.

RULES:
- Identify WHO must DO something — this is the party with an obligation, not the
  party receiving a benefit. 
  Example: if stock exchanges are told not to take penal action, the actor is 
  "Stock Exchanges and Depositories", NOT "listed entities" who merely benefit.
- Use a SHORT collective label for the actor — e.g. "MIIs", "Stock Brokers",
  "Listed entities", "Stock Exchanges and Depositories".
  Do NOT list every individual addressee by name.
- State the PRIMARY action the actor must take — the single most important
  obligation introduced by this circular.
- Use language from the circular: "shall ensure", "shall comply", "shall submit",
  "shall adopt", "are advised to", "must", etc.
- ONE SENTENCE ONLY. Hard limit — do not write two sentences under any circumstances.
  If there are multiple actions, pick the most important single one.
- If the action has a deadline or effective date, include it in that one sentence.
- Do NOT list multiple obligations or use "and" to chain actions.
- Do NOT end with annexure references or format references.
- Do NOT include background context — only the action required.
- If no specific action is required, return exactly:
  No specific action point identified.

DOCUMENT:
{text}

Return only ONE sentence. No heading. No bullet points. No second sentence.
"""

ACTION_POINT_RETRY_PROMPT = ACTION_POINT_PROMPT + """

IMPORTANT OVERRIDE:
- Re-read the circular carefully.
- Identify the party that has an OBLIGATION to act — not the party that benefits.
- Pick the MOST IMPORTANT obligation from the main operative paragraphs.
- Do NOT pick secondary administrative tasks like disseminating the circular,
  amending bye-laws, or updating websites — those are procedural follow-ups.
- Focus on the core regulatory obligation: what must be done, by whom, by when.
"""

EXISTING_PROVISION_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter.

Identify the EXISTING provision of law before the amendment.

RULES:
- Existing Provision of Law is usually described in the first few paragraphs.
- Identify the position, requirement, framework or timeline that existed before this circular.
- Mention the regulation number if available.
- Explain what the provision stated before the amendment/change ONLY if the circular explicitly describes the earlier provision.
- Do NOT infer, assume, reconstruct or deduce the pre-amendment position.
- If the circular only describes the amendment and does not explicitly state the earlier provision, return:
Not specifically stated.
- If the circular grants a relaxation, extension, exemption or modification, describe the original requirement before the relaxation.
- Extract the existing provision referred to in the circular.
- Mention the regulation number if available.
- Maximum 2 sentences.
- Do NOT describe the amendment.
- Do NOT describe the new requirement.
- Do NOT include circular numbers.
- Do NOT include legal authority paragraphs.
- If the pre-amendment provision is not expressly described in the circular, return exactly:
Not specifically stated.
- Never infer the previous legal position from the amendment itself.
- Do NOT add commentary like "not specifically stated in the document" or 
  "the circular mentions but does not explicitly state". 
  If not clearly stated, return ONLY the exact phrase: Not specifically stated.
  No additional explanation.
DOCUMENT:
{text}

Return only the existing provision.
"""

# ============================================================
# LLM HELPERS
# ============================================================

def generate_existing_provision(text: str) -> str:
    try:
        result = llm.invoke(
            EXISTING_PROVISION_PROMPT.format(text=text[:10000])
        )
        result = result.strip()

        result = re.sub(
            r'^(Existing\s+Provision\s*:?\s*)',
            '',
            result,
            flags=re.IGNORECASE
        ).strip()
        
        result = remove_annexure_references(result)
        
        # Strip LLM meta-commentary sentences
        result = re.sub(
            r'[^.]*?(?:not\s+specifically\s+stated|document\s+provided|'
            r'circular\s+mentions|does\s+not\s+explicitly)[^.]*\.',
            '',
            result,
            flags=re.IGNORECASE
        ).strip()
        
        # Strip stray closing parenthesis at end
        result = re.sub(r'\s*\)\s*$', '', result).strip()
        
        # If nothing meaningful left, return the standard phrase
        if len(result.strip()) < 10:
            return "Not specifically stated."
        
        return result

    except Exception as e:
        logging.error(f"Existing provision extraction failed: {e}")
        return "Not specifically stated."

def generate_gist(text: str, effective_date: str = "Not specified") -> str:
    try:
        result = llm.invoke(GIST_PROMPT.format(text=text[:10000]))
        result = result.strip()
        # Strip surrounding quotes LLM sometimes adds
        result = result.strip('"').strip("'").strip()

        # Remove any metadata tags the LLM might have returned
        result = re.sub(
            r'^(Gist\s*:?\s*|Summary\s*:?\s*)',
            '',
            result,
            flags=re.IGNORECASE,
        ).strip()

        result = remove_annexure_references(result)

        # ─── FIX: ANTI-DUPLICATION PIPELINE ───────────────────────────────────
        # 1. Strip the forced prefix if the LLM generated it at the very start
        result = re.sub(
            r'^SEBI has issued this circular and (?:introduced|amended|modified|clarified)\s*', 
            '', 
            result, 
            flags=re.IGNORECASE
        ).strip()
        
        # 2. Strip any messy leftover "SEBI has..." duplicate fragments that follow
        result = re.sub(
            r'^(?:SEBI has\s+(?:issued\s+this\s+circular\s+and\s+)?(?:introduced|amended|modified|clarified|granted|decided\s+to)\s+)+', 
            '', 
            result, 
            flags=re.IGNORECASE
        ).strip()

        # 3. Dynamically determine the singular correct verb based on text keywords
        if re.search(
            r'\b(?:introduc|new\s+requirement|new\s+provision|new\s+condition)\b',
            text,
            re.IGNORECASE
        ):
            verb = 'introduced'

        elif re.search(
            r'\b(?:clarif|FAQ|question)\b',
            text,
            re.IGNORECASE
        ):
            verb = 'clarified'

        elif re.search(
            r'\b(?:amend|amendment)\b',
            text,
            re.IGNORECASE
        ):
            verb = 'amended'

        else:
            verb = 'modified'

        # 4. Synthesize the clean, unified single opening sentence
        result = f"SEBI has issued this circular and {verb} " + result
        # ──────────────────────────────────────────────────────────────────────

        # Fix wrong effective date claim in gist: only replace "effective immediately"
        # when the actual effective date is a specific future date (not itself "Immediate effect")
        if (effective_date
                and effective_date not in ("Not specified", "Immediate effect")):
            result = re.sub(
                r',?\s*effective\s+immediately',
                f', effective {effective_date}',
                result,
                flags=re.IGNORECASE,
            )
            result = re.sub(
                r'with\s+immediate\s+effect',
                f'with effect from {effective_date}',
                result,
                flags=re.IGNORECASE,
            )

        # Hard safety net: truncate to 2 sentences
        sentences = re.findall(r'[^.!?]*[.!?]', result)
        if len(sentences) > 2:
            result = ' '.join(s.strip() for s in sentences[:2])

        # Hard safety net: enforce 80-word limit
        words = result.split()
        if len(words) > 80:
            result = ' '.join(words[:80]).rstrip(',;') + '.'

        return result
    except Exception as e:
        logging.error(f"Gist generation failed: {e}")
        return "Not available"    
# def generate_gist(text: str, effective_date: str = "Not specified") -> str:
#     try:
#         result = llm.invoke(GIST_PROMPT.format(text=text[:10000]))
#         result = result.strip()
#         # Strip surrounding quotes LLM sometimes adds
#         result = result.strip('"').strip("'").strip()

#         # Nuclear option: strip everything after the required opening verb 
#         # that starts a duplicate "SEBI has..."
#         result = re.sub(
#             r'(SEBI has issued this circular and\s+(?:introduced|amended|modified|clarified)\s+)'
#             r'(?:["\']?\s*SEBI has\s+(?:issued\s+this\s+circular\s+and\s+)?'
#             r'(?:introduced|amended|modified|clarified|granted|decided\s+to)\s+)?',
#             r'\1',
#             result,
#             flags=re.IGNORECASE,
#         )

#         result = re.sub(
#             r'^(Gist\s*:?\s*|Summary\s*:?\s*)',
#             '',
#             result,
#             flags=re.IGNORECASE,
#         ).strip()

#         result = remove_annexure_references(result)

#         # Fix duplicated opening generated by Mistral
#         result = re.sub(
#             r'^SEBI has issued this circular and\s+'
#             r'(?:introduced|amended|modified|clarified)\s+'
#             r'SEBI has\s+',
#             'SEBI has ',
#             result,
#             flags=re.IGNORECASE
#         ).strip()

#         if not re.match(r'sebi has issued this circular and\s+(?:introduced|amended|modified|clarified)', result, re.IGNORECASE):

#             # Pick the right verb based on keywords in the body text
#             if re.search(
#                 r'\b(?:introduc|new\s+requirement|new\s+provision|new\s+condition)\b',
#                 text,
#                 re.IGNORECASE
#             ):
#                 verb = 'introduced'

#             elif re.search(
#                 r'\b(?:clarif|FAQ|question)\b',
#                 text,
#                 re.IGNORECASE
#             ):
#                 verb = 'clarified'

#             elif re.search(
#                 r'\b(?:amend|amendment)\b',
#                 text,
#                 re.IGNORECASE
#             ):
#                 verb = 'amended'

#             else:
#                 verb = 'modified'

#             result = (
#                 f'SEBI has issued this circular and {verb} '
#                 + result
#             )
#         # Fix wrong effective date claim in gist: only replace "effective immediately"
#         # when the actual effective date is a specific future date (not itself "Immediate effect")
#         if (effective_date
#                 and effective_date not in ("Not specified", "Immediate effect")):
#             result = re.sub(
#                 r',?\s*effective\s+immediately',
#                 f', effective {effective_date}',
#                 result,
#                 flags=re.IGNORECASE,
#             )
#             result = re.sub(
#                 r'with\s+immediate\s+effect',
#                 f'with effect from {effective_date}',
#                 result,
#                 flags=re.IGNORECASE,
#             )

#         # Hard safety net: truncate to 2 sentences
#         sentences = re.findall(r'[^.!?]*[.!?]', result)
#         if len(sentences) > 2:
#             result = ' '.join(s.strip() for s in sentences[:2])

#         # Hard safety net: enforce 80-word limit
#         words = result.split()
#         if len(words) > 80:
#             result = ' '.join(words[:80]).rstrip(',;') + '.'

#         return result
#     except Exception as e:
#         logging.error(f"Gist generation failed: {e}")
#         return "Not available"


def generate_action_point(text: str) -> str:
    try:
        result = llm.invoke(ACTION_POINT_PROMPT.format(text=text[:10000]))
        result = result.strip()
        result = re.sub(
            r'^(Action\s+[Pp]oint\s*:?\s*)',
            '',
            result,
            flags=re.IGNORECASE,
        ).strip()
        result = remove_annexure_references(result)

        bad_patterns = [
            r'are\s+granted\s+(?:a\s+)?(?:one.time\s+)?relaxation',
            r'are\s+advised\s+not\s+to\s+face',
            r'will\s+not\s+face',
            r'shall\s+not\s+face',
            r'benefit\s+from',
            r'disseminat',
            r'bring.*?notice',
            r'as\s+per\s+point',      # ← catches "as per point 5"
            r'bye.?laws',              # ← catches para 5.2
            r'amend.*?rules',          # ← catches para 5.2
        ]
        for pat in bad_patterns:
            if re.search(pat, result, re.IGNORECASE):
                result = llm.invoke(
                    ACTION_POINT_RETRY_PROMPT.format(text=text[:10000])
                ).strip()
                break

        first_sentence = re.match(r'^[^.!?]*[.!?]', result)
        if first_sentence and len(first_sentence.group(0)) > 20:
            result = first_sentence.group(0).strip()
        return result
    except Exception as e:
        logging.error(f"Action point extraction failed: {e}")
        return "No specific action point identified."
# ============================================================
# SUMMARY BUILDER
# ============================================================
def build_summary(
    circular_date,
    effective_date,
    regulation_refs,
    existing_provision,
    gist,
    action_point,
)-> str:
    regulation_text = (
        "\n".join(regulation_refs[:10])
        if regulation_refs
        else "No specific regulation number cited."
    )
    return (
        f"Date of Circular:\n{circular_date}\n\n"
        f"Effective Date:\n{effective_date}\n\n"
        f"Regulation Number:\n{regulation_text}\n\n"
        f"Existing Provision of Law:\n{existing_provision}\n\n"
        f"Gist of amendment of that regulation:\n{gist}\n\n"
        f"Action point for listed entity:\n{action_point}"
    )

# ============================================================
# MAIN PROCESSOR
# ============================================================

def process_circular(pdf_path, metadata=None):
    try:
        raw_text = extract_pdf_text(pdf_path)
        body_text = extract_circular_body(raw_text)

        circular_date = extract_circular_date(raw_text)
        # Use raw_text so applicability clauses after annexure sections are not stripped
        effective_date = extract_effective_date(raw_text)
        regulation_refs = extract_regulation_references(body_text)
        gist = generate_gist(body_text, effective_date=effective_date)
        action_point = generate_action_point(body_text)
        existing_provision = generate_existing_provision(body_text)
        return {
            "summary": build_summary(
                circular_date=circular_date,
                effective_date=effective_date,
                regulation_refs=regulation_refs,
                existing_provision=existing_provision,
                gist=gist,
                action_point=action_point,
            )
        }
    except Exception as e:
        logging.error(f"Circular processing failed: {e}")
        return {"summary": "NA"}