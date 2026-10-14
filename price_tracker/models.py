import re
from dataclasses import asdict, dataclass, fields


@dataclass
class Observation:
    """One price observation of one product in one shop on one day."""

    date: str               # YYYY-MM-DD (Europe/Prague)
    scraped_at: str         # ISO timestamp UTC
    shop: str               # rohlik | kosik
    product_id: str
    name: str
    owner: str              # Coca-Cola | PepsiCo
    brand: str
    amount: str = ""        # packaging as shown by the shop, e.g. "6 x 330 ml"
    price: float | None = None           # price the customer pays now
    original_price: float | None = None  # regular (non-discounted) price
    on_sale: bool = False
    discount_pct: float | None = None
    sale_valid_till: str = ""
    promo_type: str = ""    # sale | longterm (price cut for everyone), "" = none
    multibuy_qty: int | None = None      # "buy N" offer: from N pieces ...
    multibuy_price: float | None = None  # ... each piece costs this
    unit_price: float | None = None      # current price per l / kg
    unit: str = ""
    currency: str = "CZK"
    in_stock: bool = True
    url: str = ""
    promo_info: str = ""    # raw promo details (multipack, labels...) as JSON
    store: str = ""         # store / venue within the platform (Wolt, Bolt)
    category: str = ""      # Cola, Limonády, Vody, Energy, ...
    ean: str = ""
    sponsored: bool = False  # paid placement on the platform
    lowest_30d: float | None = None  # lowest price in the last 30 days (EU Omnibus)
    liters: float | None = None      # total volume of the pack in litres
    price_per_l: float | None = None  # current price per litre, computed the same way everywhere

    def __post_init__(self):
        if self.liters is None:
            self.liters = parse_liters(f"{self.amount} {self.name}")
        if self.liters and self.price is not None:
            self.price_per_l = round(self.price / self.liters, 2)

    @classmethod
    def columns(cls):
        return [f.name for f in fields(cls)]

    def as_row(self):
        row = asdict(self)
        row["on_sale"] = int(self.on_sale)
        row["in_stock"] = int(self.in_stock)
        row["sponsored"] = int(self.sponsored)
        return {k: "" if v is None else v for k, v in row.items()}


def discount_pct(price, original):
    if price is None or not original or price >= original:
        return None
    return round((1 - price / original) * 100, 1)


_MULTI = re.compile(r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(ml|l)\b", re.IGNORECASE)
_SINGLE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l)\b", re.IGNORECASE)


def parse_liters(text):
    """'6x0,33 l' -> 1.98, '4×330ml' -> 1.32, '1,5 l' -> 1.5, '500 ml' -> 0.5."""
    text = text or ""
    m = _MULTI.search(text)
    if m:
        count, vol, unit = int(m[1]), float(m[2].replace(",", ".")), m[3].lower()
        return round(count * (vol / 1000 if unit == "ml" else vol), 3)
    m = _SINGLE.search(text)
    if m:
        vol, unit = float(m[1].replace(",", ".")), m[2].lower()
        liters = vol / 1000 if unit == "ml" else vol
        return round(liters, 3) if 0.05 <= liters <= 30 else None
    return None
