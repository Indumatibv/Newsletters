import logging
import re
from typing import List

from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama
from agents.SEBI_other_subdomains.ignore_from_pdf import (should_ignore_pdf)

# Initialize the model as per your environment
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
    """
    # if re.search(
    #     r'(?:come\s+into\s+force\s+with\s+immediate\s+effect'
    #     r'|shall\s+come\s+into\s+force\s+with\s+immediate\s+effect'
    #     r'|comes?\s+into\s+force\s+with\s+immediate\s+effect'
    #     r'|with\s+immediate\s+effect'
    #     r'|effective\s+immediately)',
    #     text,
    #     re.IGNORECASE,
    # ):
    #     return "Immediate effect"
    
    if re.search(
        r'(?:come\s+into\s+force\s+with\s+immediate\s+effect'
        r'|shall\s+come\s+into\s+force\s+with\s+immediate\s+effect'
        r'|comes?\s+into\s+force\s+with\s+immediate\s+effect'
        r'|with\s+immediate\s+effect'
        r'|effective\s+immediately'
        r'|come\s+into\s+effect\s+immediately'
        r'|shall\s+come\s+into\s+effect\s+immediately)',
        text,
        re.IGNORECASE,
    ):
        return "Immediate effect"

    ANCHOR = (
        r"(?:applicable\s+with\s+effect\s+from"
        r"|with\s+effect\s+from"
        r"|effective\s+from"
        r"|applicable\s+from"
        r"|w\.?e\.?f\.?\s*)"
    )
    for pattern in [
        rf"{ANCHOR}\s+((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"{ANCHOR}\s+(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}})",
        rf"{ANCHOR}\s+((?:{MONTHS})\s+\d{{4}})",
        rf"from\s+((?:{MONTHS})\s+\d{{4}})\s+onwards",
        rf"(?:modif(?:y|ied|ying)|revised?|implement(?:ed)?|adopt(?:ed)?)\s+(?:\w+\s+){{0,5}}from\s+((?:{MONTHS})\s+\d{{4}})",
        rf"{ANCHOR}\s+(\d{{1,2}},?\s+(?:{MONTHS}),?\s+\d{{4}})",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()
    return "Not specified"


# ============================================================
# REGULATION REFERENCE EXTRACTION
# ============================================================

def extract_primary_regulation_reference(text: str) -> str:
    header = text[:1000]
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

    m = re.search(
        r"SEBI\s+\([^)]+\)\s+Regulations(?:,?\s*\d{4})?(?:\s*\([^)]+\))?",
        header,
        re.IGNORECASE,
    )
    if m and len(m.group(0).strip()) > 10:
        return re.sub(r'\s+', ' ', m.group(0)).strip()

    return None


def extract_regulation_references(text: str) -> List[str]:
    primary = extract_primary_regulation_reference(text)
    if primary:
        return [primary]

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

    refs = {r for r in refs if not r.lower().startswith("section")}

    final_refs = []
    for ref in sorted(refs, key=len, reverse=True):
        if not any(ref.lower() in existing.lower() for existing in final_refs):
            final_refs.append(ref)

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

    schedule_refs = [r for r in final_refs if r.lower().startswith("schedule")]
    if schedule_refs:
        return schedule_refs[:3]

    return sorted(final_refs)


# ============================================================
# POST-PROCESSING CLEANUP
# ============================================================

ANNEXURE_SENTENCE_PATTERNS = [
    re.compile(
        r'[^.]*?(?:revised|updated|new|amended)\s+(?:\w+\s+)?format\s+'
        r'(?:is\s+|has\s+been\s+)?(?:enclosed|included|attached|provided|prescribed)[^.]*\.',
        re.IGNORECASE,
    ),
    re.compile(
        r'[^.]*?format\s+has\s+been\s+(?:provided|enclosed|included|attached)[^.]*\.',
        re.IGNORECASE,
    ),
    re.compile(
        r'[^.]*?(?:provided|enclosed|included|attached)\s+'
        r'(?:within|in|herewith|hereto)\s+(?:this\s+)?(?:circular|document|letter)[^.]*\.',
        re.IGNORECASE,
    ),
    re.compile(
        r',?\s*as\s+per\s+the\s+(?:prescribed|enclosed|attached|revised|above|new)\s+'
        r'(?:(?:prescribed|enclosed|attached|revised|updated|new|above)\s+)*'
        r'(?:format|document|circular|annexure)[^.]*[.]?',
        re.IGNORECASE,
    ),
    re.compile(
        r'[^.]*?(?:enclosed|attached|included)\s+in\s+this\s+circular[^.]*\.',
        re.IGNORECASE,
    ),
    re.compile(
        r'[^.]*?Annexure\s+[A-Z][^.]*\.',
        re.IGNORECASE,
    ),
    re.compile(
        r'[^.]*?(?:follows?\s+the\s+introduction|'
        r'in\s+line\s+with\s+the\s+introduction|'
        r'pursuant\s+to\s+(?:the\s+)?introduction|'
        r'following\s+the\s+introduction|'
        r'amendment\s+follows?)[^.]*\.',
        re.IGNORECASE,
    ),
    re.compile(
        r',\s*as\s+per\s+clause\s+[\d.]+\s+of\s+(?:the\s+)?'
        r'(?:Master\s+Circular|SEBI\s+Circular)\s+dated[^.]*\.',
        re.IGNORECASE,
    ),
]


def remove_annexure_references(text: str) -> str:
    for pattern in ANNEXURE_SENTENCE_PATTERNS:
        text = pattern.sub('', text)

    text = re.sub(r'\.\d+\s+of\s+[^.]+\.', '.', text)
    text = re.sub(
        r'\.\s+(?:of|as|and|or|but|which|that|where|when)\s+[^.]*\.', '.', text
    )
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+\.', '.', text)
    text = text.strip()
    return text


# ============================================================
# PROMPTS
# ============================================================

GIST_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter summary of a SEBI Circular.

Write a clean summary gist paragraph for this circular.

CRITICAL STRUCTURAL REQUIREMENT:
You must pick the most accurate past-tense action verb based on what the circular does (e.g., introduced, amended, extended, clarified, relaxed, modified).
Begin your paragraph by outputting a placeholder text using your chosen verb exactly in this format:
[VERB: your_chosen_verb] 
Immediately after the closing bracket and space, continue seamlessly into the core subject description, regulations, or framework affected. 

Do NOT wrap the [VERB: ...] tag inside any quotation marks or extra punctuation.

Example opening: [VERB: relaxed] a one-time relief framework extending the timeline...
Example opening: [VERB: amended] the regulatory lock-in mechanism for pledged securities by...

RULES:
- State clearly what framework, requirement, or timeline has been changed, introduced, or amended.
- Be detailed: State the NEW requirement, mechanism, framework, process, disclosure obligation, filing requirement, governance requirement, or compliance steps introduced by the circular.
- If the circular describes a framework issued by an intermediary (e.g., Depositories, Stock Exchanges) to operationalise an amendment, you MUST include the key steps of that framework. Do not treat "To operationalise this..." paragraphs as background — they contain mandatory operational requirements for issuers. Extract and state those requirements explicitly (e.g., AoA amendments, lender intimations, offer document disclosures).
- If the circular prescribes a framework for implementation, briefly describe the material operational requirements, disclosures, reporting obligations, governance changes, documentation requirements, stakeholder communications, system changes, or procedural steps contained in such framework.
- Do not use generic phrases such as "a framework has been prescribed", "other details are specified", or "necessary requirements have been provided". Instead briefly state the material requirements themselves.
- If the circular introduces exemption thresholds, monetary limits, or percentage-based cutoffs, you MUST state the exact figures (e.g., "1% of annual consolidated turnover or Rs. 10 crore, whichever is lower" and "Rs. 1 crore"). Do not summarise thresholds as "a specified threshold" or "below certain limits".
- Explicitly describe what regulated entities must now do.
- PROHIBITED — do NOT include background history, previous circular references, or annexure terms.
- LENGTH LIMIT: Maximum 4 sentences.
- WORD LIMIT: Maximum 150 words.
- If the circular grants relief to one party by directing another party (e.g., directing stock exchanges not to take penal action), frame the gist around what SEBI has directed, not around who receives the benefit.

DOCUMENT:
{text}

Return only the gist paragraph starting with the [VERB: ...] tag. No headings. No quotes.
"""

ACTION_POINT_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter.

Identify the active action point for the regulated entity arising from this circular.

RULES:
- Identify WHO must DO something (e.g., listed entity, issuer, merchant banker).
- State the active operational duty they must execute to achieve compliance.
- Use explicit regulatory language: "shall ensure compliance", "shall comply", "shall adopt".
- ONE SENTENCE ONLY. Hard limit.
RULES:
- Extract only an action expressly stated in the circular.
- Do not convert a benefit, exemption, relaxation, extension, waiver, or suspension into an action point.
- Do not restate the benefit granted by the circular as an action point.
- Return "No specific action point identified." only when the circular does not require any filing, disclosure, undertaking, reporting obligation, implementation step, governance change, system change, or compliance activity by any regulated entity.
- If the circular grants a relaxation subject to conditions, undertakings, disclosures, filings, confirmations, or other compliance requirements, extract those requirements as the action point.
- Only return an action point when the circular explicitly requires a filing, disclosure, undertaking, reporting obligation, system change, governance change, compliance activity, or implementation step.
- Do not frame an unconditional compliance obligation as conditional. If the circular requires entities to follow a format or standard (regardless of thresholds), state the duty as unconditional and mention the applicable format/standard, not the threshold.

DOCUMENT:
{text}

Return only ONE sentence. No heading.
"""

ACTION_POINT_RETRY_PROMPT = ACTION_POINT_PROMPT + """

IMPORTANT OVERRIDE:
- If the text implies that listed entities are simply exempt from penal actions for a time period, that is a benefit, not an active task. Return "No specific action point identified."
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
- Maximum 2 sentences.
- Do NOT describe the amendment or new requirements.
- Do NOT include circular index numbers or legal authority paragraphs.
- If the circular expressly describes the existing framework, procedure, requirement, timeline, penalty mechanism, disclosure requirement, or regulatory position before the amendment, summarize it.
- Return "Not specifically stated." only when the circular does not describe any pre-existing provision.
- Do NOT state what did not exist before. Absence of a provision is not an existing provision. If the circular only describes what was amended without stating the prior text, return: Not specifically stated.

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

        if re.search(
            r'(did\s+not\s+provide|'
            r'was\s+not\s+allowed|'
            r'was\s+not\s+extendable|'
            r'could\s+not|'
            r'previously\s+prohibited|'
            r'specific\s+mechanism\s+was\s+not\s+in\s+place|'
            r'before\s+the\s+amendment|'
            r'prior\s+to\s+the\s+amendment|'
            r'previously\s+there\s+was\s+no|'
            r'earlier\s+there\s+was\s+no)',
            result,
            re.IGNORECASE
        ):
            return "Not specifically stated."
        
        result = re.sub(r'\s*\)\s*$', '', result).strip()
        
        if len(result.strip()) < 10:
            return "Not specifically stated."
        
        return result

    except Exception as e:
        logging.error(f"Existing provision extraction failed: {e}")
        return "Not specifically stated."


def generate_gist(text: str, effective_date: str = "Not specified") -> str:
    try:
        raw_result = llm.invoke(GIST_PROMPT.format(text=text[:10000])).strip()
        raw_result = remove_annexure_references(raw_result)

        # Enhanced regex: matches [VERB: words] even if wrapped in any type of quotation marks
        verb_match = re.search(r'["\'“]?\[VERB:\s*(\w+)\]["\'”]?', raw_result, re.IGNORECASE)
        
        if verb_match:
            chosen_verb = verb_match.group(1).lower()
            # Everything after the matched tag
            summary_content = raw_result[verb_match.end():].strip()
        else:
            chosen_verb = "introduced"
            summary_content = raw_result

        # Strip accidental duplicate text prefixes or hanging quotes at the front boundary
        while True:
            cleaned = re.sub(
                r'^(?:the\s+)?(?:sebi|circular|has|issued|this|and|introduced|changed|amended|modified|clarified|extended|\s|,|\.|"|\'|“|”)+',
                '',
                summary_content,
                flags=re.IGNORECASE
            ).strip()
            if cleaned == summary_content:
                break
            summary_content = cleaned

        if summary_content:
            summary_content = summary_content[0].lower() + summary_content[1:]

        # Deterministic opening construction using the clean dynamic verb
        gist_heading = f"The SEBI has issued this circular and {chosen_verb} "
        result = gist_heading + summary_content

        # Clean up any trailing hanging quotation marks left behind at the absolute end
        result = result.strip('"').strip("'").strip('”').strip('“').strip()

        # Synchronize explicit effective dates dynamically if discovered
        if effective_date and effective_date not in ("Not specified", "Immediate effect"):
            result = re.sub(r',?\s*effective\s+immediately', f', effective {effective_date}', result, flags=re.IGNORECASE)
            result = re.sub(r'with\s+immediate\s+effect', f'with effect from {effective_date}', result, flags=re.IGNORECASE)

        # Apply strict ceiling limits
        sentences = re.findall(r'[^.!?]*[.!?]', result)
        if len(sentences) > 4:
            result = ' '.join(s.strip() for s in sentences[:4])

        # words = result.split()
        # if len(words) > 150:
        #     result = ' '.join(words[:150]).rstrip(',;') + '.'
        words = result.split()
        if len(words) > 150:
            sentences = re.findall(r'[^.!?]*[.!?]', result)
            truncated = ''
            for s in sentences:
                if len((truncated + s).split()) <= 150:
                    truncated += s
                else:
                    break
            result = truncated.strip() if truncated.strip() else ' '.join(words[:150]).rstrip(',;') + '.'
        
        return result
    except Exception as e:
        logging.error(f"Gist generation failed: {e}")
        return "Not available"


def generate_action_point(text: str) -> str:
    try:
        result = llm.invoke(ACTION_POINT_PROMPT.format(text=text[:10000])).strip()
        result = re.sub(r'^(Action\s+[Pp]oint\s*:?\s*)', '', result, flags=re.IGNORECASE).strip()
        result = remove_annexure_references(result)

        bad_patterns = [
            r'are\s+granted\s+(?:a\s+)?relaxation',
            r'benefit\s+from',
            r'disseminat',
            r'bring.*?notice',
            r'as\s+per\s+point',
            r'bye.?laws',
            r'updating\s+websites',
            r'shall\s+be\s+exempted',
            r'shall\s+be\s+exempt',
            r'exempt\s+from\s+penal',
            r'ensure\s+no\s+penal',
            r'penal\s+actions?\s+may\s+be\s+withdrawn',
            r'may\s+be\s+withdrawn'
        ]
        
        for pat in bad_patterns:
            if re.search(pat, result, re.IGNORECASE):
                result = llm.invoke(ACTION_POINT_RETRY_PROMPT.format(text=text[:10000])).strip()
                break

        first_sentence = re.match(r'^[^.!?]*[.!?]', result)
        if first_sentence and len(first_sentence.group(0)) > 20:
            result = first_sentence.group(0).strip()
            
        # Hard Pipeline Validation Fallback
        lowered_res = result.lower()

        if any(w in lowered_res for w in [
            "exempt",
            "no specific action",
            "relaxation granted",
            "no penal action"
        ]):
            return "No specific action point identified."

        if re.search(
            r'shall\s+not\s+be\s+subject\s+to\s+penal|'
            r'shall\s+not\s+be\s+liable|'
            r'may\s+avail\s+the\s+relaxation|'
            r'eligible\s+for\s+relaxation',
            lowered_res,
            re.IGNORECASE
        ):
            return "No specific action point identified."

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
) -> str:
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

# def process_circular(pdf_path, metadata=None):
def process_circular(
    pdf_path,
    issue_date=None,
    metadata=None
):
    try:
        raw_text = extract_pdf_text(pdf_path)
        if should_ignore_pdf(raw_text):

            return {
                "summary": "Pdf Ignored"
            }        
        body_text = extract_circular_body(raw_text)

        # circular_date = extract_circular_date(raw_text)
        circular_date = str(issue_date).strip()
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