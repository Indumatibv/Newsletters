import re

# ============================================================
# NORMALIZE ISSUE DATE
# ============================================================

def generate_date_patterns(issue_date):

    issue_date = str(issue_date)

    # Handle pandas timestamp strings
    issue_date = issue_date.split(" ")[0]

    year, month, day = issue_date.split("-")

    short_year = year[-2:]

    patterns = [

        rf'\b{int(day)}[\-\.]{int(month)}[\-\.]{year}\b',

        rf'\b{int(day)}[\-\.]0?{int(month)}[\-\.](?:20)?{short_year}\b'
    ]

    return [
        re.compile(p)
        for p in patterns
    ]

# ============================================================
# EDITORIAL FOOTNOTE FILTER
# ============================================================

# def is_editorial_footnote(footer_text):

#     footer_lower = footer_text.lower()

#     editorial_markers = [

#         "substituted for the word",

#         "substituted for the words",

#         "substituted for the letter",

#         "substituted for the symbol",

#         "omitted the word",

#         "inserted the word"
#     ]

#     substantive_markers = [

#         "prior to its substitution",

#         "prior to its omission",

#         "prior to its insertion",

#         "read as under"
#     ]

#     is_editorial = any(
#         marker in footer_lower
#         for marker in editorial_markers
#     )

#     has_substantive_context = any(
#         marker in footer_lower
#         for marker in substantive_markers
#     )

#     return (
#         is_editorial
#         and
#         not has_substantive_context
#     )
def is_editorial_footnote(footer_text):

    footer_lower = footer_text.lower()

    # Not an amendment footnote
    if not any(
        word in footer_lower
        for word in [
            "inserted",
            "substituted",
            "omitted"
        ]
    ):
        return True

    editorial_markers = [

        "substituted for the word",

        "substituted for the words",

        "substituted for the letter",

        "substituted for the symbol",

        "substituted for the punctuation",

        "omitted the word",

        "inserted the word"
    ]

    substantive_markers = [

        "prior to its substitution",

        "prior to its omission",

        "prior to its insertion",

        "read as under"
    ]

    is_editorial = any(
        marker in footer_lower
        for marker in editorial_markers
    )

    has_substantive_context = any(
        marker in footer_lower
        for marker in substantive_markers
    )

    return (
        is_editorial
        and
        not has_substantive_context
    )
# ============================================================
# FILTER FOOTNOTES BY ISSUE DATE
# ============================================================

def filter_footers_by_date(
    footnotes,
    issue_date
):

    filtered_footnotes = {}

    date_patterns = generate_date_patterns(
        issue_date
    )

    for footer_num, footer_text in footnotes.items():

        for pattern in date_patterns:

            # if pattern.search(footer_text):

            #     filtered_footnotes[
            #         footer_num
            #     ] = footer_text

            #     break
            if pattern.search(footer_text):

                if is_editorial_footnote(
                    footer_text
                ):

                    continue

                filtered_footnotes[
                    footer_num
                ] = footer_text

                break
    return filtered_footnotes