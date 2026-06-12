import re


# ============================================================
# SUBSECTION SPLITTING
# ============================================================

SUBSECTION_PATTERN = re.compile(r'(?:(\d+)\[)?\((\d+[A-Z]*)\)(\])?')


def _find_marker_starts(text):
    """
    Find positions of candidate subsection markers like '40[(1)]',
    '46[(2) ...', '(2B) ...'. A match is a candidate only if it occurs at
    the very start of the text, or immediately follows a closing ']' or a
    '.' (ignoring whitespace) - this filters out inline cross-references
    such as "sub-regulation (2) of regulation 34".
    """
    starts = []
    for m in SUBSECTION_PATTERN.finditer(text):
        idx = m.start()
        if idx == 0:
            valid = True
        else:
            prefix = text[:idx].rstrip()
            valid = prefix.endswith(']') or prefix.endswith('.')
        if valid:
            starts.append(m)
    return starts


def _merge_lettered_continuations(starts):
    """
    Merge lettered sub-subsections (e.g. 2A, 2B) into their base numeric
    subsection (e.g. 2) - they are continuations of the same
    sub-regulation, not separate top-level subsections.
    """
    merged = []
    for m in starts:
        sub_num = m.group(2)
        base_num = re.match(r'^\d+', sub_num).group(0)
        if merged:
            prev_num = merged[-1].group(2)
            prev_base = re.match(r'^\d+', prev_num).group(0)
            if prev_base == base_num and sub_num != base_num:
                # lettered continuation (e.g. 2A/2B following 2) - skip
                continue
        merged.append(m)
    return merged


def _is_strictly_increasing(starts):
    """
    Validate that the (merged) marker sequence forms a strictly increasing
    sequence of base numbers (e.g. 1, 2, 3 ... or 1, 2, 4). If the sequence
    repeats or decreases anywhere (a strong signal that the markers are
    actually items of a nested list, not real subsections - see
    Regulation 4), the whole sequence is rejected.
    """
    prev_base = None
    for m in starts:
        sub_num = m.group(2)
        base_num = int(re.match(r'^\d+', sub_num).group(0))
        if prev_base is not None and base_num <= prev_base:
            return False
        prev_base = base_num
    return True


def split_into_subsections(regulation_text):
    """
    Splits an already-flattened regulation text into per-subsection chunks.
    Returns a list of (subsection_number, subsection_text, footer_refs)
    tuples, or an empty list if no valid subsection markers were found
    (either none detected, or the detected sequence failed the
    strictly-increasing validation - e.g. Regulation 4's nested lists).
    """
    starts = _find_marker_starts(regulation_text)
    if not starts:
        return []

    starts = _merge_lettered_continuations(starts)

    if not _is_strictly_increasing(starts):
        return []

    segments = []
    for i, m in enumerate(starts):
        seg_start = m.start()
        seg_end = starts[i + 1].start() if i + 1 < len(starts) else len(regulation_text)
        seg_text = regulation_text[seg_start:seg_end].strip()
        sub_num = m.group(2)

        footer_refs = re.findall(r'\b(\d+)(?=\[)', seg_text)
        footer_refs = sorted(set(int(x) for x in footer_refs))

        # Strip the leading marker itself from the subsection text
        seg_text = re.sub(r'^(?:\d+\[)?\(\d+[A-Z]*\)\]?\s*', '', seg_text).strip()

        segments.append((sub_num, seg_text, footer_refs))

    return segments


# ============================================================
# MAIN ENTRYPOINT FOR PIPELINE
# ============================================================

def create_subsection_chunks(chunks):
    """
    Takes a list of section-level chunks (as produced by
    Extract_Chunks_1.process_regulation_pdf) and returns a new list where
    each chunk is further split into subsection-level chunks wherever the
    regulation text contains valid, strictly-increasing subsection markers
    (e.g. (1), (2), (2A), (2B), (3)).

    Chunks that don't have valid subsection markers (including ones where
    the marker sequence fails validation, e.g. Regulation 4's embedded
    numbered lists) are passed through unchanged, with "subsection": None.

    This operates purely in-memory on the chunks list - no file I/O.
    """
    new_chunks = []

    for chunk in chunks:
        text = chunk.get("text", "")
        subsections = split_into_subsections(text)

        if subsections:
            for sub_num, sub_text, sub_refs in subsections:
                new_chunk = dict(chunk)
                new_chunk["subsection"] = sub_num
                new_chunk["footer_reference"] = sub_refs
                new_chunk["text"] = sub_text
                new_chunks.append(new_chunk)
        else:
            new_chunk = dict(chunk)
            new_chunk["subsection"] = None
            new_chunks.append(new_chunk)

    return new_chunks