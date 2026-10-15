"""On-site search ranking: which brands a shopper sees first for generic drink queries.

The same queries, delivery address, anonymous session and default (relevance) sort on every run,
so positions are comparable over time. Only the Top 10 is kept.
"""

from .portfolio import classify

QUERIES = ["cola", "limonáda", "energy drink", "ledový čaj", "voda", "tonic"]
TOP = 10
COLUMNS = ["date", "scraped_at", "platform", "store", "query", "position", "product_id", "name",
           "owner", "brand", "sponsored", "price"]


def row(date, scraped_at, platform, store, query, position, product_id, name, brand=None,
        sponsored=False, price=None):
    hit = classify(name, brand)
    return {"date": date, "scraped_at": scraped_at, "platform": platform, "store": store, "query": query,
            "position": position, "product_id": str(product_id), "name": name or "",
            "owner": hit[0] if hit else "", "brand": hit[1] if hit else (brand or ""),
            "sponsored": int(bool(sponsored)), "price": "" if price is None else price}
