"""Reports over the price history: Markdown summary + HTML dashboard."""

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

SHOP_NAMES = {"rohlik": "Rohlík", "kosik": "Košík"}


def _fmt(v, suffix=""):
    return "" if v is None else f"{v:.2f}{suffix}".replace(".", ",")


def series(rows):
    """(shop, product_id) -> rows sorted by date."""
    out = defaultdict(list)
    for r in rows:
        out[(r["shop"], r["product_id"])].append(r)
    for v in out.values():
        v.sort(key=lambda r: r["date"])
    return out


def product_stats(rows):
    stats = []
    for (shop, pid), obs in series(rows).items():
        prices = [o["price"] for o in obs if o["price"] is not None]
        regular = [o["original_price"] for o in obs if o["original_price"] is not None]
        sale_days = sum(o["on_sale"] for o in obs)
        last = obs[-1]
        stats.append({
            "shop": shop, "product_id": pid, "name": last["name"],
            "owner": last["owner"], "brand": last["brand"], "amount": last["amount"],
            "days": len(obs), "sale_days": sale_days,
            "sale_share": sale_days / len(obs) * 100,
            "last_price": last["price"], "regular_price": last["original_price"],
            "min_price": min(prices, default=None), "max_price": max(prices, default=None),
            "avg_price": mean(prices) if prices else None,
            "max_regular": max(regular, default=None),
            "first_seen": obs[0]["date"], "last_seen": last["date"],
        })
    return stats


def price_changes(rows, date):
    """Products whose current price changed vs. their previous observation."""
    out = []
    for obs in series(rows).values():
        if obs[-1]["date"] != date or len(obs) < 2:
            continue
        prev, cur = obs[-2], obs[-1]
        if prev["price"] != cur["price"] or prev["original_price"] != cur["original_price"]:
            out.append((prev, cur))
    return out


def markdown(rows):
    if not rows:
        return "# Ceny Coca-Cola / PepsiCo\n\nZatím žádná data.\n"
    last_date = max(r["date"] for r in rows)
    today = [r for r in rows if r["date"] == last_date]
    lines = [f"# Ceny Coca-Cola / PepsiCo — {last_date}", ""]

    lines += ["## Přehled posledního scrapu", "",
              "| Obchod | Vlastník | Produktů | Ve slevě | Podíl slev |", "|---|---|---:|---:|---:|"]
    groups = defaultdict(list)
    for r in today:
        groups[(r["shop"], r["owner"])].append(r)
    for (shop, owner), g in sorted(groups.items()):
        s = sum(r["on_sale"] for r in g)
        lines.append(f"| {SHOP_NAMES.get(shop, shop)} | {owner} | {len(g)} | {s} | {s / len(g) * 100:.0f} % |")

    lines += ["", "## Průměrná cena za jednotku (Kč/l) podle značky", "",
              "| Vlastník | Značka | " + " | ".join(SHOP_NAMES.values()) + " |",
              "|---|---|" + "---:|" * len(SHOP_NAMES)]
    unit = defaultdict(list)
    for r in today:
        if r["unit_price"] is not None and r["unit"].lower() in ("l", "", "litr"):
            unit[(r["owner"], r["brand"], r["shop"])].append(r["unit_price"])
    for owner, brand in sorted({(o, b) for o, b, _ in unit}):
        cells = [_fmt(mean(unit[(owner, brand, s)])) if unit[(owner, brand, s)] else "–" for s in SHOP_NAMES]
        lines.append(f"| {owner} | {brand} | " + " | ".join(cells) + " |")

    sale = sorted((r for r in today if r["on_sale"]),
                  key=lambda r: -(r["discount_pct"] or 0))
    lines += ["", f"## Aktuální slevy ({len(sale)})", "",
              "| Obchod | Značka | Produkt | Balení | Cena | Běžná cena | Sleva | Platí do |",
              "|---|---|---|---|---:|---:|---:|---|"]
    for r in sale:
        lines.append(
            f"| {SHOP_NAMES.get(r['shop'], r['shop'])} | {r['brand']} | [{r['name']}]({r['url']}) | {r['amount']} "
            f"| {_fmt(r['price'])} | {_fmt(r['original_price'])} | {_fmt(r['discount_pct'], ' %')} "
            f"| {r['sale_valid_till'][:10]} |")

    multi = sorted((r for r in today if r.get("multibuy_qty")),
                   key=lambda r: (r["shop"], r["owner"], r["brand"], r["name"]))
    lines += ["", f"## Multikup / multipack — sleva při koupi více kusů ({len(multi)})", "",
              "| Obchod | Značka | Produkt | Balení | Cena za 1 ks | Od ks | Cena za ks | Sleva |",
              "|---|---|---|---|---:|---:|---:|---:|"]
    for r in multi:
        pct = (1 - r["multibuy_price"] / r["original_price"]) * 100 if r["original_price"] else None
        lines.append(
            f"| {SHOP_NAMES.get(r['shop'], r['shop'])} | {r['brand']} | [{r['name']}]({r['url']}) | {r['amount']} "
            f"| {_fmt(r['price'])} | {r['multibuy_qty']} | {_fmt(r['multibuy_price'])} | {_fmt(pct, ' %')} |")

    changes = price_changes(rows, last_date)
    lines += ["", f"## Změny cen oproti předchozímu měření ({len(changes)})", "",
              "| Obchod | Produkt | Předtím | Nyní | Běžná předtím | Běžná nyní |",
              "|---|---|---:|---:|---:|---:|"]
    for prev, cur in changes:
        lines.append(
            f"| {SHOP_NAMES.get(cur['shop'], cur['shop'])} | {cur['name']} ({cur['amount']}) "
            f"| {_fmt(prev['price'])} | {_fmt(cur['price'])} "
            f"| {_fmt(prev['original_price'])} | {_fmt(cur['original_price'])} |")

    stats = sorted(product_stats(rows), key=lambda s: (s["owner"], s["brand"], s["name"], s["shop"]))
    lines += ["", "## Historie produktů", "",
              "| Obchod | Značka | Produkt | Balení | Dní | Dní ve slevě | Min | Max | Průměr | Běžná |",
              "|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for s in stats:
        lines.append(
            f"| {SHOP_NAMES.get(s['shop'], s['shop'])} | {s['brand']} | {s['name']} | {s['amount']} "
            f"| {s['days']} | {s['sale_days']} ({s['sale_share']:.0f} %) | {_fmt(s['min_price'])} "
            f"| {_fmt(s['max_price'])} | {_fmt(s['avg_price'])} | {_fmt(s['regular_price'])} |")
    return "\n".join(lines) + "\n"


def dashboard(rows):
    data = []
    for (shop, pid), obs in series(rows).items():
        last = obs[-1]
        data.append({
            "key": f"{shop}:{pid}", "shop": SHOP_NAMES.get(shop, shop), "name": last["name"],
            "owner": last["owner"], "brand": last["brand"], "amount": last["amount"],
            "url": last["url"],
            "points": [[o["date"], o["price"], o["original_price"], o["on_sale"]] for o in obs],
        })
    data.sort(key=lambda d: (d["owner"], d["brand"], d["name"], d["shop"]))
    template = (Path(__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("/*DATA*/[]", payload)
