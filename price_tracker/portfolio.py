"""Brand portfolio of The Coca-Cola Company and PepsiCo (beverages, CZ market).

Each brand is matched with a regex against "<brand field> <product name>".
Extend or tweak the lists here when you find a product that is missed or
matched by mistake.
"""

import re

PORTFOLIO = {
    "Coca-Cola": {
        "Coca-Cola": r"coca[\s-]?cola|\bcoke\b",
        "Fanta": r"\bfanta\b",
        "Sprite": r"\bsprite\b",
        "Kinley": r"\bkinley\b",
        "Schweppes": r"\bschweppes\b",
        "Fuze Tea": r"\bfuze\s?tea\b",
        "Cappy": r"\bcappy\b",
        "Natura": r"\bnatura\b",
        "Römerquelle": r"\br[öo]merquelle\b",
        "Powerade": r"\bpowerade\b",
        "Monster": r"\bmonster\b",
        "Burn": r"\bburn\b",
        "Costa Coffee": r"\bcosta\s+coffee\b",
        "Smartwater": r"\bsmart\s?water\b",
        "BonAqua": r"\bbon\s?aqua\b",
    },
    "PepsiCo": {
        "Pepsi": r"\bpepsi\b",
        "7UP": r"\b7\s?up\b",
        "Mirinda": r"\bmirinda\b",
        "Mountain Dew": r"\bmountain\s+dew\b",
        "Lipton Ice Tea": r"\blipton\b.*\bice\s?tea\b|\bice\s?tea\b.*\blipton\b",
        "Rockstar": r"\brockstar\b",
        "Gatorade": r"\bgatorade\b",
    },
}

_COMPILED = [
    (owner, brand, re.compile(pattern, re.IGNORECASE))
    for owner, brands in PORTFOLIO.items()
    for brand, pattern in brands.items()
]


def classify(name, brand=None):
    """Return (owner, brand) for a portfolio product, or None."""
    text = f"{brand or ''} {name or ''}"
    for owner, brand_name, rx in _COMPILED:
        if rx.search(text):
            return owner, brand_name
    return None
