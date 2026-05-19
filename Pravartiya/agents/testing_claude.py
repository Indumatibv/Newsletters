"""
SEBI Amendment RAG Pipeline
============================

ARCHITECTURE:
  ┌─────────────────────────────────────────────────────────────┐
  │  MASTER PDF                                                  │
  │    ├── master_body.json   (regulation sections)             │
  │    └── master_footer.json (footnotes with ref numbers)      │
  │                                                              │
  │  AMENDMENT PDF                                               │
  │    └── amendment_changes.json (each numbered change)        │
  │                                                              │
  │  RAG PIPELINE (per amendment change):                        │
  │    1. Filter master_footer.json by amendment issue date      │
  │    2. For each footnote → look up full section in body JSON  │
  │    3. Build TF-IDF embeddings on those sections              │
  │    4. Similarity search → top-K chunks                       │
  │    5. Mistral (via Ollama) → structured SEBI summary         │
  └─────────────────────────────────────────────────────────────┘

Requirements:
    # Install Ollama: https://ollama.com/download
    ollama pull mistral:latest
    python sebi_rag_pipeline.py

    Ollama runs locally on http://localhost:11434 — no API key needed.
    To use a different model, change LLM_MODEL below (e.g. "llama3", "gemma3").
"""

import re
import json
import subprocess
import math
import urllib.request

# ── CONFIG ─────────────────────────────────────────────────────────────────────
MASTER_PDF_PATH    = "/Users/admin/Downloads/1777351317428.pdf"
AMENDMENT_PDF_PATH = "/Users/admin/Downloads/1769600297568.pdf"

MASTER_BODY_JSON   = "master_body.json"
MASTER_FOOTER_JSON = "master_footer.json"
AMENDMENT_JSON     = "amendment_changes.json"
OUTPUT_JSON        = "rag_output.json"

# The one amendment change being processed (per your instruction — provided manually)
TARGET_AMENDMENT_TEXT = """
In regulation 15, in sub-regulation (1A):
(i) the word "regulation" appearing after the words "regulation and" and before the
    number "16" shall be substituted with the word "regulations";
(ii) the word "regulation" appearing after the words "16 to" and before the number
    "27" shall be omitted;
(iii) the word "chapter" appearing after the number and words "27 of this" and before
    the words "shall apply to a listed entity" shall be substituted with the word "Chapter";
(iv) the word "One" appearing after the words "non-convertible debt securities of Rupees"
    and before the words "Thousand Crore" shall be substituted with the word "Five".
"""

AMENDMENT_ISSUE_DATE = "22.01.2026"   # Format in master PDF footnotes: dd.mm.yyyy
AMENDMENT_DATE_HUMAN = "20 January 2026"
EFFECTIVE_DATE       = "20 January 2026"
AMENDMENT_REG_NO     = "SEBI/NRO-GN/2026/295"

# ── LLM config (Ollama local) ─────────────────────────────────────────────────
LLM_MODEL    = "mistral:latest"          # change to "llama3", "gemma3", etc. if needed
OLLAMA_URL   = "http://localhost:11434"  # default Ollama address
# ─────────────────────────────────────────────────────────────────────────────


# ════════════════════════════════════════════════════════════════
# SECTION A: TEXT EXTRACTION
# ════════════════════════════════════════════════════════════════

def pdf_to_text(path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", path, "-"],
        capture_output=True, text=True, check=True
    )
    return result.stdout


# ════════════════════════════════════════════════════════════════
# SECTION B: PARSE MASTER PDF
# ════════════════════════════════════════════════════════════════

def parse_master_body(text: str) -> list:
    """Split master PDF text into regulation-level sections."""
    lines = text.split("\n")
    sections = []
    current_reg = None
    current_lines = []
    heading_candidate = ""
    reg_start = re.compile(r"^(\d+[A-Z]?)\.\s+\(")

    def flush():
        if current_reg and current_lines:
            sections.append({
                "regulation_num": current_reg,
                "heading":        heading_candidate,
                "full_text":      "\n".join(current_lines).strip(),
            })

    for line in lines:
        clean = line.replace("\f", "").strip()
        m = reg_start.match(clean)
        if m:
            flush()
            current_reg = m.group(1)
            current_lines = [clean]
            heading_candidate = ""
        elif current_reg:
            if re.match(r"^[A-Z][A-Za-z ,/\-\[\]']+\.$", clean) and len(clean) < 120:
                heading_candidate = clean
            current_lines.append(clean)
        else:
            if re.match(r"^[A-Z][A-Za-z ,/\-\[\]']+\.$", clean) and len(clean) < 120:
                heading_candidate = clean

    flush()
    return sections


def parse_master_footnotes(text: str) -> list:
    """
    Parse footnotes from master PDF.

    Footnote format (after pdftotext -layout):
        80                              <- standalone number on its own line
        Substituted for "regulation"    <- footnote body (multi-line)
        81                              <- next ref starts

    Returns list of dicts with ref_num, amendment_date, action,
    full_note, prior_text, regulation_num.
    """
    lines = text.split("\n")
    footnotes = []
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r"^\d{1,3}$", stripped):
            ref_num = stripped
            body_lines = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if re.match(r"^\d{1,3}$", nxt):
                    break
                body_lines.append(nxt)
                j += 1
            body = " ".join(body_lines).strip()

            if re.search(r"(Substituted|Inserted|Omitted|vide|w\.e\.f)", body, re.IGNORECASE):
                # Date
                date_m = re.search(r"w\.e\.f\.?\s*([\d.]+)", body)
                raw    = date_m.group(1).rstrip(".") if date_m else ""
                parts  = raw.split(".")
                norm   = (f"{int(parts[0]):02d}.{int(parts[1]):02d}.{parts[2]}"
                          if len(parts) == 3 else raw)

                # Action
                act_m  = re.match(r"(Substituted|Inserted|Omitted)", body, re.IGNORECASE)
                if not act_m:
                    act_m = re.search(r"\b(omitted|inserted|substituted)\b", body, re.IGNORECASE)
                action = act_m.group(1).lower() if act_m else "unknown"

                # Prior text
                prior_m = re.search(
                    r'[Pp]rior to.*?(?:read as (?:under|follows)|the (?:provision|clause|sub-regulation|regulation|explanation) read)\s*[:\s"]+(.+)',
                    body, re.DOTALL
                )
                prior_text = prior_m.group(1).strip().strip('"').strip() if prior_m else ""

                # Regulation context: scan backwards for last "XX. (" line
                reg_context = ""
                for k in range(i - 1, max(0, i - 500), -1):
                    rm = re.match(r"^(\d+[A-Z]?)\.\s+\(", lines[k].strip())
                    if rm:
                        reg_context = rm.group(1)
                        break

                footnotes.append({
                    "ref_num":        ref_num,
                    "amendment_date": norm,
                    "action":         action,
                    "full_note":      body,
                    "prior_text":     prior_text,
                    "regulation_num": reg_context,
                })
            i = j
        else:
            i += 1

    return footnotes


# ════════════════════════════════════════════════════════════════
# SECTION C: PARSE AMENDMENT PDF
# ════════════════════════════════════════════════════════════════

def parse_amendment_pdf(text: str) -> dict:
    effective_on_pub = bool(re.search(
        r"come into force on the date of (?:their |its )?publication", text, re.IGNORECASE
    ))
    date_m  = re.search(r"(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})", text)
    notif_m = re.search(r"No\.\s+SEBI/[A-Z\-/0-9]+", text)

    eng_idx = text.find("SECURITIES AND EXCHANGE BOARD OF INDIA (LISTING OBLIGATIONS AND DISCLOSURE")
    if eng_idx == -1:
        eng_idx = text.find("No. SEBI/NRO-GN")
    eng_text = text[eng_idx:] if eng_idx != -1 else text

    roman   = r"(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XIV|XV|XVI|XVII|XVIII|XIX|XX)"
    chg_pat = re.compile(rf"(?m)^\s*({roman})\.\s+in regulation\s+(\w+)", re.MULTILINE)
    matches = list(chg_pat.finditer(eng_text))
    changes = []
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(eng_text)
        changes.append({
            "change_num":  m.group(1),
            "regulation":  m.group(2),
            "change_text": eng_text[m.start():end].strip(),
        })

    return {
        "gazette_date":     date_m.group(1) if date_m else "",
        "effective_on_pub": effective_on_pub,
        "notif_num":        notif_m.group(0) if notif_m else "",
        "total_changes":    len(changes),
        "changes":          changes,
    }


# ════════════════════════════════════════════════════════════════
# SECTION D: EMBEDDINGS & SIMILARITY
# ════════════════════════════════════════════════════════════════

def tfidf_vector(text: str) -> dict:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    freq  = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq


def cosine_similarity(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    keys  = set(a) & set(b)
    dot   = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


def build_chunks(sections: list, all_footnotes: list) -> list:
    chunks = []
    for sec in sections:
        reg        = sec["regulation_num"]
        reg_notes  = [f for f in all_footnotes if f["regulation_num"] == reg]
        fn_text    = "\n".join(
            f"[Ref {fn['ref_num']}] {fn['action'].title()}: {fn['full_note']}"
            for fn in reg_notes
        )
        combined   = f"{sec['full_text']}\n\n--- FOOTNOTES ---\n{fn_text}"
        chunks.append({
            "regulation_num": reg,
            "heading":        sec.get("heading", ""),
            "full_text":      sec["full_text"],
            "footnotes":      reg_notes,
            "combined_text":  combined,
            "vector":         tfidf_vector(combined),
        })
    return chunks


def similarity_search(query: str, chunks: list, top_k: int = 3) -> list:
    q_vec  = tfidf_vector(query)
    scored = [(cosine_similarity(q_vec, c["vector"]), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


# ════════════════════════════════════════════════════════════════
# SECTION E: GENERATE SUMMARY
# ════════════════════════════════════════════════════════════════

def build_context_block(chunks: list) -> str:
    parts = []
    for chunk in chunks:
        reg     = chunk["regulation_num"]
        heading = chunk.get("heading", "")
        body    = chunk["full_text"]

        prior_rows = []
        new_rows   = []
        for fn in chunk.get("footnotes", []):
            if fn["action"] == "omitted" and fn["prior_text"]:
                prior_rows.append(f"  • [Ref {fn['ref_num']}] OMITTED: {fn['prior_text'][:300]}")
            elif fn["action"] == "substituted":
                if fn["prior_text"]:
                    prior_rows.append(f"  • [Ref {fn['ref_num']}] PRIOR: {fn['prior_text'][:300]}")
                new_rows.append(f"  • [Ref {fn['ref_num']}] {fn['full_note'][:250]}")
            elif fn["action"] == "inserted":
                new_rows.append(f"  • [Ref {fn['ref_num']}] INSERTED: {fn['full_note'][:250]}")

        part = (
            f"╔══ REGULATION {reg}" + (f" — {heading}" if heading else "") + " ══╗\n"
            f"CURRENT TEXT:\n{body[:2500]}\n\n"
        )
        if prior_rows:
            part += "EXISTING PROVISIONS PRIOR TO THIS AMENDMENT:\n" + "\n".join(prior_rows) + "\n\n"
        if new_rows:
            part += "AMENDMENT ACTIONS (from footnotes):\n" + "\n".join(new_rows) + "\n"
        part += "╚" + "═" * 60 + "╝"
        parts.append(part)
    return "\n\n".join(parts)


def call_ollama(prompt: str, model: str = LLM_MODEL, ollama_url: str = OLLAMA_URL) -> str:
    """
    Call Ollama's local REST API (no API key required).
    Ollama must be running: `ollama serve` or the desktop app.
    """
    payload = json.dumps({
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,   # low temp = more deterministic/factual
            "num_predict": 2048,
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response", "").strip()
    except Exception as e:
        raise RuntimeError(
            f"Ollama call failed: {e}\n"
            f"Make sure Ollama is running (`ollama serve`) and the model is pulled "
            f"(`ollama pull {model}`)."
        )


def generate_summary(amendment_text, chunks, amendment_date, effective_date, notif_num):
    context = build_context_block(chunks)

    # Mistral works best with a single combined prompt (no separate system role via /api/generate)
    prompt = f"""[INST] You are a senior legal analyst specializing in SEBI (Securities and Exchange Board of India) regulations.
Produce a structured summary of the SEBI amendment below for a compliance team at a listed entity.

STRICT RULES:
1. Sub Domain must be: Regulations
2. Opening MUST start with: "The SEBI has issued this circular and [introduced/changed/amended]..."
3. Closing MUST be: "Action point for listed entity: [specific action]"
4. NEVER reference internal ref numbers, footnote numbers, or circular index numbers.
5. NEVER include email addresses.
6. Be SPECIFIC about the substantive legal/regulatory effect — do not just say "word X substituted with word Y".
7. "Existing provisions" must describe what the old law said in plain language.
8. If the change is purely editorial/clarificatory with no substantive legal effect, state that explicitly.

OUTPUT FORMAT (follow exactly):
---
Sub Domain: Regulations

Date of Circular: {amendment_date}
Effective Date: {effective_date}

Gist of Amendment:
[2-3 sentences on what changed and why it matters]

Existing Provisions Prior to Amendment:
[Plain language of what the law said before this amendment]

Summary:
[Full paragraph starting with "The SEBI has issued this circular and..."]

Action Point for Listed Entity:
[Specific compliance action required, or "No immediate action required — editorial/clarificatory amendment only."]
---

AMENDMENT TEXT (from gazette):
{amendment_text}

RETRIEVED CONTEXT FROM MASTER SEBI LODR REGULATIONS (Regulation 15 — current text + footnotes):
{context}
[/INST]"""

    print(f"      Calling Ollama ({LLM_MODEL}) at {OLLAMA_URL}...")
    return call_ollama(prompt)


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  SEBI Amendment RAG Pipeline")
    print("=" * 65)

    print("\n[1/6] Extracting text from PDFs...")
    master_text    = pdf_to_text(MASTER_PDF_PATH)
    amendment_text = pdf_to_text(AMENDMENT_PDF_PATH)
    print(f"      Master: {len(master_text):,} chars | Amendment: {len(amendment_text):,} chars")

    print("\n[2/6] Parsing master body sections...")
    body_sections = parse_master_body(master_text)
    print(f"      Sections found: {len(body_sections)}")
    with open(MASTER_BODY_JSON, "w", encoding="utf-8") as f:
        json.dump(body_sections, f, indent=2, ensure_ascii=False)
    print(f"      Saved → {MASTER_BODY_JSON}")

    print("\n[3/6] Parsing master footnotes...")
    all_footnotes = parse_master_footnotes(master_text)
    print(f"      Total footnotes: {len(all_footnotes)}")
    with open(MASTER_FOOTER_JSON, "w", encoding="utf-8") as f:
        json.dump(all_footnotes, f, indent=2, ensure_ascii=False)
    print(f"      Saved → {MASTER_FOOTER_JSON}")

    dated_footnotes = [f for f in all_footnotes if f["amendment_date"] == AMENDMENT_ISSUE_DATE]
    print(f"      Footnotes for {AMENDMENT_ISSUE_DATE}: {len(dated_footnotes)}")
    regs_affected = sorted(set(f["regulation_num"] for f in dated_footnotes if f["regulation_num"]))
    print(f"      Regulations affected: {regs_affected}")

    print("\n[4/6] Parsing amendment PDF...")
    amendment_data = parse_amendment_pdf(amendment_text)
    with open(AMENDMENT_JSON, "w", encoding="utf-8") as f:
        json.dump(amendment_data, f, indent=2, ensure_ascii=False)
    print(f"      Changes in gazette: {amendment_data['total_changes']}")
    print(f"      Effective on publication: {amendment_data['effective_on_pub']}")
    print(f"      Saved → {AMENDMENT_JSON}")

    print("\n[5/6] Building embeddings & similarity search...")
    reg_map           = {s["regulation_num"]: s for s in body_sections}
    # Smart: force-include regulations explicitly named in the amendment text
    mentioned = re.findall(r"regulation\s+(\d+[A-Z]?)", TARGET_AMENDMENT_TEXT)
    priority  = sorted(set(mentioned) | set(regs_affected))
    affected_sections = [reg_map[r] for r in priority if r in reg_map]
    if not affected_sections:
        print("      WARNING: fallback to full body search")
        affected_sections = body_sections

    chunks     = build_chunks(affected_sections, dated_footnotes)
    top_chunks = similarity_search(TARGET_AMENDMENT_TEXT, chunks, top_k=3)
    print(f"      Top {len(top_chunks)} chunks selected:")
    for c in top_chunks:
        print(f"        → Regulation {c['regulation_num']}  ({len(c.get('footnotes',[]))} footnotes)")

    print("\n[6/6] Generating structured summary via Claude API...")
    summary = generate_summary(
        amendment_text = TARGET_AMENDMENT_TEXT,
        chunks         = top_chunks,
        amendment_date = AMENDMENT_DATE_HUMAN,
        effective_date = EFFECTIVE_DATE,
        notif_num      = AMENDMENT_REG_NO,
    )

    print("\n" + "=" * 65)
    print("  STRUCTURED SUMMARY")
    print("=" * 65)
    print(summary)

    output = {
        "amendment_reg_no":      AMENDMENT_REG_NO,
        "amendment_date":        AMENDMENT_DATE_HUMAN,
        "effective_date":        EFFECTIVE_DATE,
        "issue_date_filter":     AMENDMENT_ISSUE_DATE,
        "footnotes_matched":     len(dated_footnotes),
        "regulations_affected":  regs_affected,
        "retrieved_regulations": [c["regulation_num"] for c in top_chunks],
        "summary":               summary,
        "all_dated_footnotes":   dated_footnotes,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Full output saved → {OUTPUT_JSON}")


if __name__ == "__main__":
    main()