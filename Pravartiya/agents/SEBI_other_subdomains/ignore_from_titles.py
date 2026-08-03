# import re

# IGNORE_TITLE_PATTERNS = [

#     r"\bmutual\s+funds?\b",
#     r"\bkra\b",
#     r"\bkras\b",

#     r"\baif\b",
#     r"alternative\s+investment\s+fund",

#     r"\binvit\b",
#     r"infrastructure\s+investment\s+trust",

#     r"\bniveshak\s+shivir\b",

#     r"\binauguration\b",

#     r"\bsurvey\b",

#     r"\bmunicipal\s+bond\b",

#     r"\bcontest\b",

#     r"\bcampaign\b",

#     r"\bannual\s+report\b",

#     r"\bnewspaper\s+advertisement\b",

#     r"\bintermediaries?\b",

#     r"\bresearch\s+analyst\b",

#     r"\bstock\s+broker\b",
#     r"\bstock\s+brocker\b",

#     r"\bportfolio\s+investors?\b",

#     r"\breal\s+estate\s+investment\s+trust\b",

#     r"\bcollective\s+investment\s+scheme\b",

#     r"\bcredit\s+rating\s+agenc(?:y|ies)\b",

#     r"\bportfolio\s+management\b",

#     r"\bstock\s+exchanges?\b",

#     r"\bstock\s+exchanges?\s+and\s+clearing\s+corporations?\b"
# ]

# COMPILED_IGNORE_PATTERNS = [
#     re.compile(p, re.IGNORECASE)
#     for p in IGNORE_TITLE_PATTERNS
# ]


# def should_ignore_title(title: str) -> bool:

#     if not isinstance(title, str):
#         return False

#     title = title.strip()

#     return any(
#         pattern.search(title)
#         for pattern in COMPILED_IGNORE_PATTERNS
#     )

import re

IGNORE_TITLE_PATTERNS = [
    r"\bmutual\s+funds?\b",
    r"\bkra\b",
    r"\bkras\b",

    r"\baif\b",
    r"alternative\s+investment\s+funds?",

    r"\binvit\b",
    r"infrastructure\s+investment\s+trust",

    r"\bniveshak\s+shivir\b",

    r"\binauguration\b",

    r"\bsurvey\b",

    r"\bmunicipal\s+bond\b",
    r"\bminicipal\s+bond\b",   # common misspelling

    r"\bcontest\b",

    r"\bcampaign\b",

    r"\bannual\s+report\b",

    r"\bnewspaper\s+advertisement\b",

    r"\bintermediaries?\b",

    r"\bresearch\s+analyst\b",

    r"\bstock\s+broker\b",
    r"\bstock\s+brocker\b",    # common misspelling

    r"\bportfolio\s+investors?\b",

    r"\breal\s+estate\s+investment\s+trust\b",

    r"\bcollective\s+investment\s+scheme\b",

    r"\bcredit\s+rating\s+agenc(?:y|ies)\b",

    r"\bportfolio\s+management\b",

    r"\bstock\s+exchanges?\b",

    r"\bstock\s+exchanges?\s+and\s+clearing\s+corporations?\b",

    # New additions
    r"\basset\s+management\s+companies?\b",
    r"\basset\s+management\s+company\b",
    r"\bamc\b",

    r"\bmargin\s+trading\s+facility\b",

    r"\bregulated\s+entities?\b",

    r"\bdebenture\s+trustees?\b",
]

COMPILED_IGNORE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in IGNORE_TITLE_PATTERNS
]


def should_ignore_title(title: str) -> bool:
    if not isinstance(title, str):
        return False

    title = title.strip()

    return any(
        pattern.search(title)
        for pattern in COMPILED_IGNORE_PATTERNS
    )