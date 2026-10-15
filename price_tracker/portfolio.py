"""Tracked beverage portfolios on the Czech market.

Each brand is matched with a regex against "<brand field> <product name>".
Owners are the companies that run the brand in CZ (e.g. Pepsi is PepsiCo's
brand, bottled and distributed in CZ by Mattoni 1873; Schweppes in CZ is
produced by Mattoni 1873). Extend or tweak the lists here when a product is
missed or matched by mistake.
"""

import re

# brand -> (regex, default category)
PORTFOLIO = {
    "Coca-Cola": {
        "Coca-Cola": (r"coca[\s-]?cola|\bcoke\b", "Cola"),
        "Fanta": (r"\bfanta\b", "Limonády"),
        "Sprite": (r"\bsprite\b", "Limonády"),
        "Kinley": (r"\bkinley\b", "Tonic a mixery"),
        "Fuze Tea": (r"\bfuze\s?tea\b", "Ledové čaje"),
        "Cappy": (r"\bcappy\b", "Džusy"),
        "Natura": (r"\bnatura\b", "Vody"),
        "Römerquelle": (r"\br[öo]merquelle\b", "Vody"),
        "Powerade": (r"\bpowerade\b", "Sportovní"),
        "Monster": (r"\bmonster\b", "Energy"),
        "Burn": (r"\bburn\b", "Energy"),
        "Costa Coffee": (r"\bcosta\s+coffee\b", "Ledová káva"),
        "Smartwater": (r"\bsmart\s?water\b", "Vody"),
        "BonAqua": (r"\bbon\s?aqua\b", "Vody"),
    },
    "PepsiCo": {
        "Pepsi": (r"\bpepsi\b", "Cola"),
        "7UP": (r"\b7\s?up\b", "Limonády"),
        "Mirinda": (r"\bmirinda\b", "Limonády"),
        "Mountain Dew": (r"\bmountain\s+dew\b", "Limonády"),
        "Lipton Ice Tea": (r"\blipton\b.*\bice\s?tea\b|\bice\s?tea\b.*\blipton\b", "Ledové čaje"),
        "Rockstar": (r"\brockstar\b", "Energy"),
        "Gatorade": (r"\bgatorade\b", "Sportovní"),
    },
    "Kofola": {
        "Kofola": (r"\bkofola\b", "Cola"),
        "Citro Cola": (r"\bcitro\s?cola\b", "Cola"),
        "Rajec": (r"\brajec\b", "Vody"),
        "Korunní": (r"\bkorunn[ií]\b", "Vody"),
        "Ondrášovka": (r"\bondr[aá][sš]ovka\b", "Vody"),
        "Kláštorná": (r"\bkl[aá][sš]torn[aá]\b", "Vody"),
        "Šaratica": (r"\b[sš]aratica\b", "Vody"),
        "Vinea": (r"\bvinea\b", "Limonády"),
        "Top Topic": (r"\btop\s?topic\b", "Limonády"),
        "Jupí": (r"\bjup[ií]\b", "Sirupy"),
        "Jupík": (r"\bjup[ií]k\b", "Dětské nápoje"),
        "Semtex": (r"\bsemtex\b", "Energy"),
        "UGO": (r"\bugo\b", "Džusy"),
    },
    "Mattoni": {
        "Mattoni": (r"\bmattoni\b", "Vody"),
        "Magnesia": (r"\bmagnesia\b", "Vody"),
        "Aquila": (r"\baquila\b", "Vody"),
        "Poděbradka": (r"\bpod[eě]bradka\b", "Vody"),
        "Dobrá voda": (r"\bdobr[aá]\s+voda\b", "Vody"),
        "Hanácká kyselka": (r"\bhan[aá]ck[aá]\s+kyselka\b", "Vody"),
        "Schweppes": (r"\bschweppes\b", "Tonic a mixery"),
    },
    "Red Bull": {
        "Red Bull": (r"\bred\s?bull\b", "Energy"),
    },
    # Italian lemonades: Targa Limonata / citron competes with Sprite, Aranciata / pomeranč with Fanta.
    "Targa Florio": {
        "Targa Limonata": (r"\btarga\b.*\b(limonata|limone|citr[oó]n|citrus|lemon)", "Limonády"),
        "Targa Aranciata": (r"\btarga\b.*\b(aranci|pomeran|orange)", "Limonády"),
        "Targa": (r"\btarga\b", "Limonády"),
    },
}

# Licensed / non-comparable products that mention a tracked brand.
EXCLUDE = re.compile(r"sodastream|capri[\s-]?sun|\bgin\b|\brum\b|vodka|whisk|tuháček|\bsirup\b.*\bpepsi\b",
                     re.IGNORECASE)

# Product-name keywords that override the brand's default category.
CATEGORY_HINTS = [
    (re.compile(r"(?i)energy|energetick"), "Energy"),
    (re.compile(r"(?i)ledov[ýy] [čc]aj|ice\s?tea|\btea\b"), "Ledové čaje"),
    (re.compile(r"(?i)tonic|ginger\s?ale|bitter\s?lemon"), "Tonic a mixery"),
    (re.compile(r"(?i)sirup"), "Sirupy"),
    (re.compile(r"(?i)\bcola\b|kofola"), "Cola"),
]

_COMPILED = [
    (owner, brand, re.compile(pattern, re.IGNORECASE), category)
    for owner, brands in PORTFOLIO.items()
    for brand, (pattern, category) in brands.items()
]
# Jupík must win over Jupí, Citro Cola over generic cola brands.
_COMPILED.sort(key=lambda c: c[1] not in ("Jupík", "Citro Cola"))

OWNERS = list(PORTFOLIO)


def classify(name, brand=None):
    """Return (owner, brand) for a tracked product, or None."""
    hit = classify_full(name, brand)
    return hit[:2] if hit else None


def classify_full(name, brand=None):
    """Return (owner, brand, category) for a tracked product, or None."""
    text = f"{brand or ''} {name or ''}"
    if EXCLUDE.search(text):
        return None
    for owner, brand_name, rx, category in _COMPILED:
        if rx.search(text):
            if category not in ("Vody", "Džusy", "Dětské nápoje"):
                for hint_rx, hint in CATEGORY_HINTS:
                    if hint_rx.search(name or ""):
                        category = hint
                        break
            return owner, brand_name, category
    return None
