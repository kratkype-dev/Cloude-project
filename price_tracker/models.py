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
    unit_price: float | None = None      # current price per l / kg
    unit: str = ""
    currency: str = "CZK"
    in_stock: bool = True
    url: str = ""
    promo_info: str = ""    # raw promo details (multipack, labels...) as JSON

    @classmethod
    def columns(cls):
        return [f.name for f in fields(cls)]

    def as_row(self):
        row = asdict(self)
        row["on_sale"] = int(self.on_sale)
        row["in_stock"] = int(self.in_stock)
        return {k: "" if v is None else v for k, v in row.items()}


def discount_pct(price, original):
    if price is None or not original or price >= original:
        return None
    return round((1 - price / original) * 100, 1)
