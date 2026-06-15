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

            if pattern.search(footer_text):

                filtered_footnotes[
                    footer_num
                ] = footer_text

                break

    return filtered_footnotes