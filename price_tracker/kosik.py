"""Kosik.cz scraper using the site's internal front-end JSON API.

Flow: GET /api/front/menu/main (category tree) -> find "Nápoje" -> walk the
subtree -> GET /api/front/page/products?slug=<category>&limit=30 for each leaf,
then POST /api/front/products/more {cursor, limit} for the next pages -> keep
Coca-Cola / PepsiCo portfolio.

Discount fields: `price` (current), `recommendedPrice` (regular),
`percentageDiscount`, `actionLabel` ("Akce platí do 27. 10."),
`cumulativePrices` (Multikup: lower price per piece from N pieces).
"""

import json
import logging
import re
import urllib.parse
from collections import Counter

from . import coverage, search
from .http import Http
from .models import Observation, discount_pct
from .portfolio import classify, classify_full

log = logging.getLogger(__name__)

BASE = "https://www.kosik.cz"
ROOT_CATEGORY = re.compile(r"^nápoje$", re.IGNORECASE)
EXCLUDE_CATEGORY = re.compile(
    r"alkohol|pivo|piva|víno|vína|lihovin|destilát|káva|kávy|sekt|šampaň",
    re.IGNORECASE,
)
PAGE_LIMIT = 30
PROMO_KEYS = ("actionLabel", "labels", "priceLabels", "cumulativePrices",
              "loyaltyClubBenefitsPrice")
VALID_TILL = re.compile(r"do\s+(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{4}))?")


def _children(node):
    return node.get("subcategories") or node.get("subCategories") or []


def _slug(url):
    return urllib.parse.urlparse(url).path.lstrip("/")


class Kosik:
    shop = "kosik"

    def __init__(self, http=None, slugs=None):
        self.http = http or Http(BASE)
        self.slugs = slugs
        self.coverage = []

    def banners(self, date):
        """Category banners in the drinks section (main + 1st level)."""
        menu = self.http.get_json("/api/front/menu/main")
        stack, roots = list(menu.get("categories", [])), []
        while stack:
            node = stack.pop()
            if ROOT_CATEGORY.search(node.get("name", "")):
                roots.append(node)
            stack.extend(_children(node))
        if not roots:
            return []
        node = max(roots, key=lambda n: len(_children(n)))  # the main drinks section, not a nested "Nápoje"
        slugs = [(node["name"], _slug(node["url"]))] + [
            (c["name"], _slug(c["url"])) for c in _children(node)
            if not EXCLUDE_CATEGORY.search(c.get("name", ""))]
        rows = []
        for name, slug in slugs:
            data = self.http.get_json("/api/front/page/products", {"slug": slug, "limit": 1})
            for i, b in enumerate(data.get("banners") or []):
                title, owner, brand = self._banner_target(b)
                rows.append({
                    "date": date, "platform": "kosik", "placement": f"Banner v kategorii {name}",
                    "position": i + 1, "title": title, "owner": owner, "brand": brand,
                    "link": b.get("link") or "",
                    "image": ((b.get("images") or {}).get("main") or "").replace("WIDTHxHEIGHTx1", "1530x388x1"),
                })
        return rows

    def _banner_target(self, banner):
        """Name and brands of a banner from the page it links to (the banner text itself is only in the image).

        Returns (title, owner, brands): title of the landing page or product, the owner with most
        products on it and up to three tracked brands by frequency.
        """
        link = banner.get("link") or ""
        url = urllib.parse.urlparse(link)
        slug = url.path.lstrip("/")
        title, names = "", []
        try:
            if re.match(r"p\d+", slug):
                product = self.http.get_json(f"/api/front/product/slug/{slug}").get("product") or {}
                title = product.get("name") or ""
                names = [(title, (product.get("brand") or {}).get("name") if isinstance(product.get("brand"), dict) else None)]
            elif slug:
                page = self.http.get_json("/api/front/page/products",
                                          {"slug": slug, "limit": PAGE_LIMIT, **dict(urllib.parse.parse_qsl(url.query))})
                title = page.get("title") or ""
                for item in (page.get("products") or {}).get("items", []):
                    b = item.get("brand")
                    names.append((item.get("name"), b.get("name") if isinstance(b, dict) else b))
        except Exception as e:  # landing page gone: fall back to the banner's internal name
            log.info("Kosik banner target %s: %s", link, e)
        hits = [h for h in (classify(n, b) for n, b in names) if h]
        if not hits:  # e.g. a product link of an untracked brand, or no landing page
            h = classify(re.sub(r"[-_/]", " ", f"{banner.get('name', '')} {link}"))
            hits = [h] if h else []
        owners = Counter(o for o, _ in hits)
        brands = [b for b, _ in Counter(b for _, b in hits).most_common(3)]
        title = title or banner.get("caption") or _banner_title(banner.get("name"))
        return title, (owners.most_common(1)[0][0] if owners else ""), ", ".join(brands)

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
        data = self.http.get_json("/api/front/page/products", {"slug": slug, "limit": PAGE_LIMIT})
        products = data.get("products") or {}
        yield from products.get("items", [])
        cursor = products.get("cursor")
        while cursor:
            page = self.http.post_json("/api/front/products/more",
                                       {"cursor": cursor, "limit": PAGE_LIMIT})
            if not page.get("products"):
                return
            yield from page["products"]
            cursor = page.get("cursor")

    def scrape(self, date, scraped_at):
        seen, failed = {}, 0
        slugs = self.leaf_slugs()
        for slug in slugs:
            try:  # one broken category must not hide the rest, but it makes the run partial
                for item in self.items(slug):
                    seen.setdefault(item.get("id"), item)
            except Exception as e:
                log.warning("Kosik category %s failed: %s", slug, e)
                failed += 1
        log.info("Kosik: %d drinks found", len(seen))
        out = []
        for item in seen.values():
            brand = item.get("brand")
            hit = classify_full(item.get("name"), brand.get("name") if isinstance(brand, dict) else brand)
            if hit:
                out.append(parse_item(item, hit, date, scraped_at))
        self.coverage.append(coverage.entry("kosik", "", "ceny", len(slugs), failed, len(out),
                                            f"{len(seen)} nápojů v {len(slugs)} kategoriích"))
        return out

    def search_ranking(self, date, scraped_at):
        """Top 10 of the site search (the /vyhledavani page). Košík does not label sponsored search results."""
        rows, failed = [], 0
        for q in search.QUERIES:
            try:
                data = self.http.get_json("/api/front/page/products",
                                          {"slug": "vyhledavani", "search_term": q, "limit": search.TOP})
            except Exception as e:
                log.warning("Kosik search %r failed: %s", q, e)
                failed += 1
                continue
            for pos, item in enumerate(((data.get("products") or {}).get("items") or [])[:search.TOP], 1):
                b = item.get("brand")
                rows.append(search.row(date, scraped_at, "kosik", "", q, pos, item.get("id"), item.get("name"),
                                       b.get("name") if isinstance(b, dict) else b, False, item.get("price")))
        self.coverage.append(coverage.entry("kosik", "", "vyhledavani", len(search.QUERIES), failed,
                                            note="Košík sponzorované výsledky ve vyhledávání neoznačuje"))
        return rows


def _banner_title(name):
    """'cat_kozel-W41' -> 'Kozel (kampaň, týden 41)'."""
    m = re.match(r"(?:cat_)?(.+?)(?:-W(\d+))?$", name or "")
    if not m:
        return name or ""
    title = m[1].replace("-", " ").replace("_", " ").strip().capitalize()
    return f"{title} (týden {m[2]})" if m[2] else title


def _valid_till(label, date):
    """'Akce platí do 27. 10.' -> '2026-10-27' (year inferred from scrape date)."""
    m = VALID_TILL.search(label or "")
    if not m:
        return ""
    day, month, year = int(m[1]), int(m[2]), int(m[3] or date[:4])
    if not m[3] and month < int(date[5:7]):  # e.g. scraped in December, valid till January
        year += 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_item(item, hit, date, scraped_at):
    price = item.get("price")
    recommended = item.get("recommendedPrice")
    original = recommended if recommended and price is not None and recommended > price else price
    pct = item.get("percentageDiscount") or discount_pct(price, original)
    qty = item.get("productQuantity") or {}
    amount = " ".join(str(x).replace(".", ",") for x in (qty.get("prefix"), qty.get("value"), qty.get("unit")) if x)
    per_unit = item.get("pricePerUnit") or {}
    promo = {k: item[k] for k in PROMO_KEYS if item.get(k)}
    multi = min(item.get("cumulativePrices") or [], key=lambda c: c.get("quantity") or 0, default=None)
    on_sale = bool(pct) and pct > 0
    return Observation(
        date=date,
        scraped_at=scraped_at,
        shop="kosik",
        product_id=str(item.get("id")),
        name=item.get("name") or "",
        owner=hit[0],
        brand=hit[1],
        category=hit[2],
        amount=amount,
        price=price,
        original_price=original,
        on_sale=on_sale,
        discount_pct=pct or None,
        sale_valid_till=_valid_till(item.get("actionLabel"), date) if on_sale else "",
        promo_type="sale" if on_sale else "",
        multibuy_qty=multi.get("quantity") if multi else None,
        multibuy_price=multi.get("price") if multi else None,
        unit_price=per_unit.get("price"),
        unit=per_unit.get("unit") or "",
        in_stock=not item.get("firstOrderDay"),
        url=urllib.parse.urljoin(BASE, item.get("url") or ""),
        promo_info=json.dumps(promo, ensure_ascii=False) if promo else "",
    )
