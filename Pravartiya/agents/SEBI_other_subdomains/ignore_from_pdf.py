import logging

IGNORE_TARGETS = [

    "all recognised stock exchanges",

    "all recognized stock exchanges",

    "all depositories",

    "all registered merchant bankers",

    "all issuers who have listed/propose to list green debt securities",

    "all mutual funds",

    "all amcs",

    "all trustees",

    "all amfi",

    "all registered investment advisers",

    "all research analysts",

    "all registered custodians",

    "all aifs",

    "all ivca",

    "all stock brokers",

    "all dps",

    "all rtas",

    "all ias",

    "all ras",

    "all invits",

    "all reits",

    "all pms",
]


def should_ignore_pdf(text: str) -> bool:

    header = text.lower()[:3000]

    # Highest priority
    if "all listed entities" in header:
        return False

    for target in IGNORE_TARGETS:

        if target in header:

            logging.info(
                f"Ignoring PDF because addressed to: {target}"
            )

            return True

    return False