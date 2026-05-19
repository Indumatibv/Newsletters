import json
import re

def filter_footers_by_date(input_json_path, output_json_path):
    # --------------------------------------------------------
    # Load all footers
    # --------------------------------------------------------
    with open(input_json_path, "r", encoding="utf-8") as f:
        all_footers = json.load(f)

    filtered_footers = {}

    # --------------------------------------------------------
    # Target date regex for Jan 22, 2026
    # Matches: 22-01-2026, 22-1-2026, 22.01.2026, 22.1.2026, 22-1-26, 22.01.26 etc.
    # --------------------------------------------------------
    date_pattern = re.compile(
        r'\b22[\-\.]0?1[\-\.](?:20)?26\b'
    )

    # --------------------------------------------------------
    # Scan and filter
    # --------------------------------------------------------
    for footer_num, footer_text in all_footers.items():
        if date_pattern.search(footer_text):
            filtered_footers[footer_num] = footer_text

    # --------------------------------------------------------
    # Save the filtered subset
    # --------------------------------------------------------
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(filtered_footers, f, indent=4, ensure_ascii=False)

    print(f"Filtering complete! Found {len(filtered_footers)} footnotes matching '22-01-2026' or '22.01.2026'.")
    print(f"Saved to '{output_json_path}'.")

if __name__ == "__main__":
    INPUT_PATH = "all_footers.json"
    OUTPUT_PATH = "filtered_footers.json"
    
    filter_footers_by_date(INPUT_PATH, OUTPUT_PATH)