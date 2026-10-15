"""Rohlik.cz scraper using the site's internal JSON API (no login needed).

Flow: find the "Nápoje" category -> walk its subtree -> list product IDs of
each leaf category -> fetch product cards (name, brand, prices) in batches ->
keep Coca-Cola / PepsiCo portfolio -> enrich with /products/prices (promo
types such as multipacks).

Prices depend on the delivery address in the session; anonymous requests get
the default (Prague) assortment.
"""

import json
import logging
import re

from . import coverage, search
from .http import Http
from .models import Observation, discount_pct
from .portfolio import classify_full

log = logging.getLogger(__name__)

BASE = "https://www.rohlik.cz"
ROOT_CATEGORY = re.compile(r"^nápoje$", re.IGNORECASE)
EXCLUDE_CATEGORY = re.compile(
    r"alkohol|pivo|piva|víno|vína|lihovin|destilát|káva|kávy|sekt|šampaň|horké",
    re.IGNORECASE,
)
# Sale types in /products/prices. "premium" (Xtra members only) and
# "expiration" (damaged / near expiry) are not a public price cut.
PUBLIC_SALES = {"sale": "sale", "longtermAction": "longterm"}
PAGE_SIZE = 50
CARD_BATCH = 30


class Rohlik:
    shop = "rohlik"

    def __init__(self, http=None, category_ids=None):
        self.http = http or Http(BASE)
        self.category_ids = category_ids
        self.category_names = {}
        self.sponsored = {}  # productId -> category name where it is a paid placement
        self.coverage = []

    # --- categories -------------------------------------------------------
    def _subcategories(self, category_id=None):
        suffix = f"/{category_id}" if category_id else ""
        data = self.http.get_json(f"/api/v1/categories/normal{suffix}/subcategories")
        return data.get("categoryIds", [])

    def _names(self, ids):
        if not ids:
            return {}
        data = self.http.get_json(
            "/api/v1/categories", [("categories", i) for i in ids] + [("type", "normal")]
        )
        return {c["categoryId"]: c.get("name", "") for c in data}

    def leaf_categories(self):
        if self.category_ids:
            return list(self.category_ids)
        top = self._names(self._subcategories())
        roots = [cid for cid, name in top.items() if ROOT_CATEGORY.search(name)]
        if not roots:
            raise RuntimeError(f"Rohlik: root category not found among {list(top.values())}")
        leaves, stack = [], list(roots)
        while stack:
            cid = stack.pop()
            children = self._names(self._subcategories(cid))
            self.category_names.update(children)
            kept = [c for c, n in children.items() if not EXCLUDE_CATEGORY.search(n)]
            if not children:
                leaves.append(cid)
            stack.extend(kept)
        log.info("Rohlik: %d leaf categories under Nápoje", len(leaves))
        return leaves

    # --- products ---------------------------------------------------------
    def product_ids(self, category_id):
        page = 0
        while True:
            data = self.http.get_json(
                f"/api/v1/categories/normal/{category_id}/products",
                {"page": page, "size": PAGE_SIZE, "sort": "recommended",
                 "filter": "", "excludeProductIds": ""},
            )
            ids = data.get("productIds", [])
            for imp in data.get("impressions") or []:
                self.sponsored.setdefault(imp.get("productId"), self.category_names.get(category_id, str(category_id)))
            yield from ids
            if len(ids) < PAGE_SIZE:
                return
            page += 1

    def cards(self, ids):
        for i in range(0, len(ids), CARD_BATCH):
            batch = ids[i:i + CARD_BATCH]
            yield from self.http.get_json(
                "/api/v1/products/card",
                [("products", p) for p in batch] + [("categoryType", "normal")],
            )

    def promos(self, ids):
        """productId -> list of active sales (type, price, ...)."""
        out = {}
        for i in range(0, len(ids), CARD_BATCH):
            batch = ids[i:i + CARD_BATCH]
            try:
                data = self.http.get_json(
                    "/api/v1/products/prices", [("products", p) for p in batch]
                )
            except Exception as e:  # promo details are a nice-to-have
                log.warning("Rohlik: prices endpoint failed: %s", e)
                continue
            for item in data:
                out[item.get("productId")] = item.get("sales") or []
        return out

    def scrape(self, date, scraped_at):
        seen, failed = {}, 0
        leaves = self.leaf_categories()
        for cid in leaves:
            try:  # one broken category must not hide the rest, but it makes the run partial
                seen.update(dict.fromkeys(self.product_ids(cid)))
            except Exception as e:
                log.warning("Rohlik category %s failed: %s", cid, e)
                failed += 1
        seen = list(seen)
        log.info("Rohlik: %d drinks found, fetching cards", len(seen))

        matched = []
        for card in self.cards(seen):
            hit = classify_full(card.get("name"), card.get("brand"))
            if hit:
                matched.append((card, hit))
        promos = self.promos([c["productId"] for c, _ in matched])
        out = [parse_card(c, hit, promos.get(c["productId"]), date, scraped_at)
               for c, hit in matched]
        for o in out:
            o.sponsored = int(o.product_id) in self.sponsored
        self.coverage.append(coverage.entry("rohlik", "", "ceny", len(leaves), failed, len(out),
                                            f"{len(seen)} nápojů v {len(leaves)} kategoriích"))
        self.banner_rows = [
            {"date": date, "platform": "rohlik", "placement": f"Sponzorovaný produkt – {self.sponsored[int(o.product_id)]}",
             "position": 1, "title": o.name, "owner": o.owner, "brand": o.brand, "link": o.url, "image": ""}
            for o in out if o.sponsored
        ]
        return out

    def banners(self, date):
        """Sponsored products of tracked brands (collected during scrape)."""
        return getattr(self, "banner_rows", [])

    def search_ranking(self, date, scraped_at):
        """Top 10 of the site search for each generic query; `impressions` are the sponsored results."""
        rows, failed = [], 0
        for q in search.QUERIES:
            try:
                data = self.http.get_json("/services/frontend-service/search-metadata",
                                          {"search": q, "offset": 0, "limit": search.TOP, "companyId": 1,
                                           "canCorrect": "true"})["data"]
            except Exception as e:
                log.warning("Rohlik search %r failed: %s", q, e)
                failed += 1
                continue
            ads = {i.get("productId") for i in data.get("impressions") or []}
            for pos, p in enumerate((data.get("productList") or [])[:search.TOP], 1):
                rows.append(search.row(date, scraped_at, "rohlik", "", q, pos, p.get("productId"),
                                       p.get("productName"), p.get("brand"), p.get("productId") in ads,
                                       (p.get("price") or {}).get("full")))
        self.coverage.append(coverage.entry("rohlik", "", "vyhledavani", len(search.QUERIES), failed))
        return rows


def _amount(v):
    return (v or {}).get("amount") if isinstance(v, dict) else v


def parse_card(card, hit, sales, date, scraped_at):
    prices = card.get("prices") or {}
    original = prices.get("originalPrice")
    price = original
    promo_type, valid_till, multibuy = "", "", None
    if sales is None:  # prices endpoint unavailable -> fall back to the card
        if prices.get("salePrice") is not None:
            price, promo_type = prices["salePrice"], "sale"
            valid_till = prices.get("saleValidTill") or ""
    else:
        for s in sales:
            if s.get("active") is False:
                continue
            kind = s.get("type")
            amount = _amount(s.get("price"))
            if kind in PUBLIC_SALES and (s.get("triggerAmount") or 1) == 1 and amount is not None:
                if amount < (price or float("inf")):
                    price, promo_type = amount, PUBLIC_SALES[kind]
                    original = original or _amount(s.get("originalPrice"))
                    valid_till = s.get("validTill") or ""
            elif kind == "multipack" and amount is not None:
                multibuy = (s.get("triggerAmount"), amount)
    # The card's unitPrice belongs to the price the card shows (sale or regular);
    # rescale it to the price we record.
    shown, unit_price = prices.get("salePrice") or original, prices.get("unitPrice")
    if unit_price and shown and price:
        unit_price = round(unit_price * price / shown, 2)
    stock = (card.get("stock") or {}).get("availabilityStatus", "AVAILABLE")
    pid = card.get("productId")
    slug = card.get("slug") or ""
    return Observation(
        date=date,
        scraped_at=scraped_at,
        shop="rohlik",
        product_id=str(pid),
        name=card.get("name") or "",
        owner=hit[0],
        brand=hit[1],
        category=hit[2],
        amount=card.get("textualAmount") or "",
        price=price,
        original_price=original,
        on_sale=bool(promo_type),
        discount_pct=discount_pct(price, original),
        sale_valid_till=valid_till,
        promo_type=promo_type,
        multibuy_qty=multibuy[0] if multibuy else None,
        multibuy_price=multibuy[1] if multibuy else None,
        unit_price=unit_price,
        unit=card.get("unit") or "",
        currency=prices.get("currency") or "CZK",
        in_stock=stock == "AVAILABLE",
        url=f"{BASE}/{pid}-{slug}" if slug else f"{BASE}/{pid}",
        promo_info=json.dumps(sales, ensure_ascii=False) if sales else "",
    )
