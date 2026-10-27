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

from . import coverage, search
from .http import Http
from .models import Observation, discount_pct
from .portfolio import classify_full

log = logging.getLogger(__name__)

BASE = "https://consumer-api.wolt.com"
LAT, LON = 50.0755, 14.4378  # Praha – náměstí Míru
# Front-page banners are checked from several addresses: the carousel is local.
BANNER_LOCATIONS = {
    "Vinohrady": (LAT, LON),
    "Karlín": (50.0925, 14.4510),
    "Staré Město": (50.0870, 14.4210),
    "Dejvice": (50.1030, 14.3910),
    "Chodov": (50.0335, 14.4920),
}

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
        self.coverage = []

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
            seen, cats, failed = {}, [], 0
            try:
                cats = self.drink_categories(venue)
            except Exception as e:  # one closed / renamed store must not kill the run
                log.warning("Wolt %s failed: %s", venue, e)
                self.coverage.append(coverage.entry("wolt", store, "ceny", 1, 1, note=str(e)))
                continue
            for cat in cats:
                try:
                    for item in self.items(venue, cat):
                        seen.setdefault(item["id"], item)
                except Exception as e:
                    log.warning("Wolt %s / %s failed: %s", venue, cat, e)
                    failed += 1
            n = 0
            for item in seen.values():
                hit = classify_full(item.get("name"))
                if hit:
                    out.append(parse_item(item, hit, venue, store, date, scraped_at))
                    n += 1
            log.info("Wolt %s: %d drinks, %d tracked", store, len(seen), n)
            self.coverage.append(coverage.entry("wolt", store, "ceny", len(cats), failed, n,
                                                f"{len(seen)} nápojů v {len(cats)} kategoriích"))
        return out

    def search_ranking(self, date, scraped_at):
        """Top 10 of the in-store search of each venue; advertising_info marks a sponsored result."""
        rows = []
        for venue, store in self.venues.items():
            failed = 0
            for q in search.QUERIES:
                try:
                    data = self.http.post_json(f"{self._assortment(venue)}/items/search?language=cs", {"q": q})
                except Exception as e:
                    log.warning("Wolt search %s %r failed: %s", venue, q, e)
                    failed += 1
                    continue
                for pos, item in enumerate((data.get("items") or [])[:search.TOP], 1):
                    rows.append(search.row(date, scraped_at, "wolt", store, q, pos, f"{venue}:{item.get('id')}",
                                           item.get("name"), None, bool(item.get("advertising_info")),
                                           _price(item.get("price"))))
            self.coverage.append(coverage.entry("wolt", store, "vyhledavani", len(search.QUERIES), failed))
        return rows

    def banners(self, date):
        """Hero carousel and curated banner sections on the Wolt front page, seen from several Prague addresses.

        The carousel differs by address and time of day, so one address misses banners. Sponsored (Wolt Ads)
        banners for logged-in users are not in the anonymous page at all: those come from manual captures.
        """
        seen = {}
        for area, (lat, lon) in BANNER_LOCATIONS.items():
            try:
                data = self.http.get_json("/v1/pages/front", {"lat": lat, "lon": lon})
            except Exception as e:
                log.warning("Wolt front page %s failed: %s", area, e)
                continue
            for section in data.get("sections", []):
                template = section.get("template") or ""
                if not template.startswith("banner") or section.get("name") in ("category-list", "socialmedia"):
                    continue
                for i, item in enumerate(section.get("items") or []):
                    title = item.get("title") or ""
                    key = (template, title)
                    if key in seen:
                        seen[key]["areas"].append(area)
                        continue
                    link = item.get("link") or {}
                    # The brand is often only in the description ("Red Bull s příchutí ..."), not in the title.
                    hit = classify_full(f"{title} {item.get('description') or ''}")
                    seen[key] = {"date": date, "platform": "wolt", "section": section.get("name"), "areas": [area],
                                 "position": i + 1, "title": title,
                                 "owner": hit[0] if hit else "", "brand": hit[1] if hit else "",
                                 "link": link.get("target") or "", "image": (item.get("image") or {}).get("url", "")}
        rows = []
        for r in seen.values():
            areas = r.pop("areas")
            r["placement"] = f"Úvodní stránka – {r.pop('section')} ({', '.join(areas)})"
            rows.append(r)
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
