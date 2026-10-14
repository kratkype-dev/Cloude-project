"""Wolt scraper: retail chains selling on Wolt (Tesco, Albert, PENNY, Žabka, ...).

Uses Wolt's consumer assortment API (no login):
  GET /consumer-api/consumer-assortment/v1/venues/slug/{venue}/assortment
      -> category tree of the store
  GET .../assortment/categories/slug/{category}?page_token=...
      -> items with price, original_price, unit_price, EAN, lowest 30-day price,
         advertising_info (sponsored placement)
Front page banners: GET /v1/pages/front?lat=&lon=
"""

import json
import logging
import re

from .http import Http
from .models import Observation, discount_pct
from .portfolio import classify_full

log = logging.getLogger(__name__)

BASE = "https://consumer-api.wolt.com"
LAT, LON = 50.0755, 14.4378  # Praha – náměstí Míru

# venue slug -> display name. One store per chain, central Prague.
VENUES = {
    "tesco-hypermarket-narodni": "Tesco Národní",
    "albert-vinohradska": "Albert Vinohradská",
    "penny-praha-vysehrad": "PENNY Vyšehrad",
    "zabka-rimska": "Žabka Římská",
}
DRINKS = re.compile(r"(?i)nápoj|napoj|limon|vod[ay]|minerál|džus|dzus|energ|cola|sirup|ledov|sport|nealko")
EXCLUDE = re.compile(r"(?i)vín|vin[ay]\b|piv|cider|lihov|alkohol|káv|kav[ay]|čaj(?!e? ledov)|instant|mléč")


def _price(v):
    return None if v is None else round(v / 100, 2)


class Wolt:
    shop = "wolt"

    def __init__(self, http=None, venues=None):
        self.http = http or Http(BASE)
        self.venues = venues or VENUES

    def _assortment(self, venue):
        return f"/consumer-api/consumer-assortment/v1/venues/slug/{venue}/assortment"

    def drink_categories(self, venue):
        tree = self.http.get_json(self._assortment(venue), {"language": "cs"})["categories"]
        out = []
        for top in tree:
            subs = top.get("subcategories") or []
            if DRINKS.search(top.get("name", "")) and subs:
                out += [c["slug"] for c in subs if not EXCLUDE.search(c.get("name", ""))]
            elif DRINKS.search(top.get("name", "")) and not EXCLUDE.search(top.get("name", "")):
                out.append(top["slug"])
        return out

    def items(self, venue, category):
        params = {"language": "cs"}
        while True:
            data = self.http.get_json(f"{self._assortment(venue)}/categories/slug/{category}", params)
            yield from data.get("items", [])
            token = (data.get("metadata") or {}).get("next_page_token")
            if not token or not data.get("items"):
                return
            params = {"language": "cs", "page_token": token}

    def scrape(self, date, scraped_at):
        out = []
        for venue, store in self.venues.items():
            try:
                seen = {}
                for cat in self.drink_categories(venue):
                    for item in self.items(venue, cat):
                        seen.setdefault(item["id"], item)
            except Exception as e:  # one closed / renamed store must not kill the run
                log.warning("Wolt %s failed: %s", venue, e)
                continue
            n = 0
            for item in seen.values():
                hit = classify_full(item.get("name"))
                if hit:
                    out.append(parse_item(item, hit, venue, store, date, scraped_at))
                    n += 1
            log.info("Wolt %s: %d drinks, %d tracked", store, len(seen), n)
        return out

    def banners(self, date):
        """Hero carousel and curated sections on the Wolt front page (Prague)."""
        data = self.http.get_json("/v1/pages/front", {"lat": LAT, "lon": LON})
        rows = []
        for pos, section in enumerate(data.get("sections", [])):
            template = section.get("template") or ""
            if not template.startswith("banner") or section.get("name") in ("category-list", "socialmedia"):
                continue
            for i, item in enumerate(section.get("items") or []):
                link = item.get("link") or {}
                hit = classify_full(item.get("title"))
                rows.append({
                    "date": date, "platform": "wolt", "placement": f"Úvodní stránka – {section.get('name')}",
                    "position": i + 1, "title": item.get("title") or "",
                    "owner": hit[0] if hit else "", "brand": hit[1] if hit else "",
                    "link": link.get("target") or "", "image": (item.get("image") or {}).get("url", ""),
                })
        return rows


def parse_item(item, hit, venue, store, date, scraped_at):
    price, original = _price(item.get("price")), _price(item.get("original_price"))
    on_sale = original is not None and price is not None and price < original
    validity = item.get("item_price_discount_validity_period") or {}
    unit = item.get("unit_price") or {}
    return Observation(
        date=date,
        scraped_at=scraped_at,
        shop="wolt",
        store=store,
        product_id=f"{venue}:{item.get('id')}",
        name=item.get("name") or "",
        owner=hit[0],
        brand=hit[1],
        category=hit[2],
        amount=item.get("unit_info") or "",
        price=price,
        original_price=original if on_sale else price,
        on_sale=on_sale,
        discount_pct=discount_pct(price, original) if on_sale else None,
        sale_valid_till=(validity.get("end") or "") if isinstance(validity, dict) else "",
        promo_type="sale" if on_sale else "",
        unit_price=_price(unit.get("price")),
        unit="l" if unit.get("unit") == "litre" else (unit.get("unit") or ""),
        in_stock=not item.get("disabled_info"),
        url=f"https://wolt.com/cs/cze/prague/venue/{venue}",
        ean=item.get("barcode_gtin") or "",
        sponsored=bool(item.get("advertising_info")),
        lowest_30d=_price(item.get("lowest_price")),
        promo_info=json.dumps(item["advertising_info"], ensure_ascii=False) if item.get("advertising_info") else "",
    )
