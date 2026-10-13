"""Kosik.cz scraper using the site's internal front-end JSON API.

Flow: GET /api/front/menu/main (category tree) -> find "Nápoje" -> walk the
subtree -> GET /api/front/page/products?slug=<category>&limit=30 for each leaf,
following the `more` link for pagination -> keep Coca-Cola / PepsiCo portfolio.

Discount fields: `price` (current), `recommendedPrice` (regular),
`percentageDiscount`.
"""

import json
import logging
import re
import urllib.parse

from .http import Http
from .models import Observation, discount_pct
from .portfolio import classify

log = logging.getLogger(__name__)

BASE = "https://www.kosik.cz"
ROOT_CATEGORY = re.compile(r"^nápoje$", re.IGNORECASE)
EXCLUDE_CATEGORY = re.compile(
    r"alkohol|pivo|piva|víno|vína|lihovin|destilát|káva|kávy|sekt|šampaň",
    re.IGNORECASE,
)
PAGE_LIMIT = 30
PROMO_KEYS = ("labels", "badges", "flags", "actions", "action", "discount",
              "multipack", "quantityDiscount")


def _children(node):
    return node.get("subcategories") or node.get("subCategories") or []


def _slug(url):
    return urllib.parse.urlparse(url).path.lstrip("/")


class Kosik:
    shop = "kosik"

    def __init__(self, http=None, slugs=None):
        self.http = http or Http(BASE)
        self.slugs = slugs

    def leaf_slugs(self):
        if self.slugs:
            return list(self.slugs)
        menu = self.http.get_json("/api/front/menu/main")
        roots, stack = [], list(menu.get("categories", []))
        while stack:  # the drinks node may be nested (e.g. under a "Potraviny" group)
            node = stack.pop()
            if ROOT_CATEGORY.search(node.get("name", "")):
                roots.append(node)
            else:
                stack.extend(_children(node))
        if not roots:
            raise RuntimeError("Kosik: 'Nápoje' category not found in menu")
        leaves, stack = [], roots
        while stack:
            node = stack.pop()
            kids = [k for k in _children(node) if not EXCLUDE_CATEGORY.search(k.get("name", ""))]
            if _children(node):
                stack.extend(kids)
            else:
                leaves.append(_slug(node["url"]))
        log.info("Kosik: %d leaf categories under Nápoje", len(leaves))
        return leaves

    def items(self, slug):
        path, params = "/api/front/page/products", {"slug": slug, "limit": PAGE_LIMIT}
        while path:
            data = self.http.get_json(path, params)
            yield from (data.get("products") or {}).get("items", [])
            path, params = data.get("more"), None

    def scrape(self, date, scraped_at):
        seen = {}
        for slug in self.leaf_slugs():
            for item in self.items(slug):
                seen.setdefault(item.get("id"), item)
        log.info("Kosik: %d drinks found", len(seen))
        out = []
        for item in seen.values():
            hit = classify(item.get("name"), item.get("brand"))
            if hit:
                out.append(parse_item(item, hit, date, scraped_at))
        return out


def parse_item(item, hit, date, scraped_at):
    price = item.get("price")
    recommended = item.get("recommendedPrice")
    original = recommended if recommended and price is not None and recommended > price else price
    pct = item.get("percentageDiscount") or discount_pct(price, original)
    qty = item.get("productQuantity") or {}
    amount = " ".join(str(x).replace(".", ",") for x in (qty.get("prefix"), qty.get("value"), qty.get("unit")) if x)
    per_unit = item.get("pricePerUnit") or {}
    promo = {k: item[k] for k in PROMO_KEYS if item.get(k)}
    return Observation(
        date=date,
        scraped_at=scraped_at,
        shop="kosik",
        product_id=str(item.get("id")),
        name=item.get("name") or "",
        owner=hit[0],
        brand=hit[1],
        amount=amount,
        price=price,
        original_price=original,
        on_sale=bool(pct) and pct > 0,
        discount_pct=pct or None,
        unit_price=per_unit.get("price"),
        unit=per_unit.get("unit") or "",
        in_stock=not item.get("firstOrderDay"),
        url=urllib.parse.urljoin(BASE, item.get("url") or ""),
        promo_info=json.dumps(promo, ensure_ascii=False) if promo else "",
    )
