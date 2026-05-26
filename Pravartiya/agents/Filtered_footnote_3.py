# import json
# import re

# def filter_footers_by_date(input_json_path, output_json_path):
#     # --------------------------------------------------------
#     # Load all footers
#     # --------------------------------------------------------
#     with open(input_json_path, "r", encoding="utf-8") as f:
#         all_footers = json.load(f)

#     filtered_footers = {}

#     # --------------------------------------------------------
#     # Target date regex for Jan 22, 2026
#     # Matches: 22-01-2026, 22-1-2026, 22.01.2026, 22.1.2026, 22-1-26, 22.01.26 etc.
#     # --------------------------------------------------------
#     date_pattern = re.compile(
#         r'\b22[\-\.]0?1[\-\.](?:20)?26\b'
#     )

#     # --------------------------------------------------------
#     # Scan and filter
#     # --------------------------------------------------------
#     for footer_num, footer_text in all_footers.items():
#         if date_pattern.search(footer_text):
#             filtered_footers[footer_num] = footer_text

#     # --------------------------------------------------------
#     # Save the filtered subset
#     # --------------------------------------------------------
#     with open(output_json_path, "w", encoding="utf-8") as f:
#         json.dump(filtered_footers, f, indent=4, ensure_ascii=False)

#     print(f"Filtering complete! Found {len(filtered_footers)} footnotes matching '22-01-2026' or '22.01.2026'.")
#     print(f"Saved to '{output_json_path}'.")

# if __name__ == "__main__":
#     INPUT_PATH = "all_footers.json"
#     OUTPUT_PATH = "filtered_footers.json"
    
#     filter_footers_by_date(INPUT_PATH, OUTPUT_PATH)

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