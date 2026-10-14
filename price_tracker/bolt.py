"""Bolt Food scraper: retail stores selling on Bolt Food (Tesco, Žabka).

Uses Bolt's public (no login) delivery client API on deliveryuser.live.boltsvc.net:
  GET /deliveryClient/public/searchInMenu?provider_id=&search_string=
      -> menu items with price, availability, promo keys
The API requires app-style query params (deviceId, deviceType, version, ...),
which the web app sends as well.
"""

import html
import json
import logging
import uuid

from .http import Http
from .models import Observation, discount_pct
from .portfolio import PORTFOLIO, classify_full

log = logging.getLogger(__name__)

BASE = "https://deliveryuser.live.boltsvc.net"
LAT, LNG = 50.0755, 14.4378  # Praha – náměstí Míru

# provider id -> display name
PROVIDERS = {
    126587: "Tesco Národní",
    146338: "Žabka Legerova",
}


def _search_terms():
    return sorted({brand.lower() for brands in PORTFOLIO.values() for brand in brands})


class Bolt:
    shop = "bolt"

    def __init__(self, http=None, providers=None):
        self.http = http or Http(BASE, delay=1.5)
        self.providers = providers or PROVIDERS
        self.base = {
            "deviceId": str(uuid.uuid4()), "deviceType": "web", "device_name": "Chrome",
            "device_os_version": "Linux", "language": "cs-CZ", "version": "FW.1.200",
            "delivery_lat": LAT, "delivery_lng": LNG,
        }

    def search(self, provider_id, term):
        data = self.http.get_json("/deliveryClient/public/searchInMenu",
                                  {**self.base, "provider_id": provider_id, "search_string": term})
        if data.get("code") != 0:
            raise RuntimeError(f"Bolt search failed: {data.get('message')}")
        data = data["data"]
        promos = data.get("menu_promos") or {}
        for item in (data.get("items") or {}).values():
            if item.get("type") == "dish":
                yield item, promos.get(item.get("promo_key")) if item.get("promo_key") else None

    def scrape(self, date, scraped_at):
        out = []
        for pid, store in self.providers.items():
            seen = {}
            try:
                for term in _search_terms():
                    for item, promo in self.search(pid, term):
                        seen.setdefault(item["id"], (item, promo))
            except Exception as e:
                log.warning("Bolt %s failed: %s", store, e)
                continue
            n = 0
            for item, promo in seen.values():
                hit = classify_full(html.unescape((item.get("name") or {}).get("value") or ""))
                if hit:
                    out.append(parse_item(item, promo, hit, pid, store, date, scraped_at))
                    n += 1
            log.info("Bolt %s: %d search hits, %d tracked", store, len(seen), n)
        return out


def _ean(product_id):
    """Bolt's product_id is the EAN for some stores, an internal code for others."""
    pid = str(product_id or "")
    return pid if pid.isdigit() and len(pid) in (8, 13) and not pid.startswith(("2", "02")) else ""


def parse_item(item, promo, hit, pid, store, date, scraped_at):
    p = item.get("price") or {}
    price = p.get("value")
    original = p.get("old_value") or p.get("original_value") or (p.get("original") or {}).get("value")
    on_sale = bool(original and price is not None and price < original)
    name = html.unescape((item.get("name") or {}).get("value") or "")
    return Observation(
        date=date,
        scraped_at=scraped_at,
        shop="bolt",
        store=store,
        product_id=f"{pid}:{item.get('product_id') or item.get('id')}",
        name=name,
        owner=hit[0],
        brand=hit[1],
        category=hit[2],
        price=price,
        original_price=original if on_sale else price,
        on_sale=on_sale,
        discount_pct=discount_pct(price, original) if on_sale else None,
        promo_type="sale" if on_sale else "",
        in_stock=item.get("availability") == "in_stock",
        url=f"https://food.bolt.eu/cs-CZ/271-prague/p/{pid}",
        ean=_ean(item.get("product_id")),
        promo_info=json.dumps(promo, ensure_ascii=False) if promo else "",
    )
