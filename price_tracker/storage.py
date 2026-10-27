"""Append-only history stored as monthly CSV files (git friendly).

data/history/YYYY-MM.csv: one row per observation (run, shop, product). Rows are never rewritten:
a second run on the same day adds its own rows (scraped_at is the run's UTC time) and `load`
keeps the latest observation of each product per day. Saving the same run twice adds nothing.
data/coverage/YYYY-MM.csv: what each run managed to load (see coverage.py).
data/search/YYYY-MM.csv: Top 10 search results per query.
"""

import csv
from pathlib import Path

from .models import Observation
from .portfolio import EXCLUDE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_DIR = DATA_DIR / "history"


def save(observations, history_dir=HISTORY_DIR):
    rows = [o.as_row() for o in observations]
    return _append(rows, history_dir, Observation.columns(), ("date", "scraped_at", "shop", "product_id"),
                   lambda r: (r["date"], r["shop"], r.get("store", ""), r["owner"], r["brand"], r["name"], r["scraped_at"]))


def _append(rows, directory, columns, key, sort_key=None):
    """Add rows to monthly files, skipping rows whose key is already stored (idempotent re-save)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for r in rows:
        by_month.setdefault(r["date"][:7], []).append(r)
    added = 0
    for month, new in by_month.items():
        path = directory / f"{month}.csv"
        old = _read(path)
        known = {tuple(str(r.get(k, "")) for k in key) for r in old}
        fresh = [r for r in new if tuple(str(r.get(k, "")) for k in key) not in known]
        if not fresh:
            continue
        added += len(fresh)
        out = old + [{c: r.get(c, "") for c in columns} for r in fresh]
        if sort_key:
            out.sort(key=sort_key)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            w.writerows(out)
    return added


def _read(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(history_dir=HISTORY_DIR):
    """One row per (date, shop, product) from all months, numeric fields converted."""
    latest = {}
    for path in sorted(Path(history_dir).glob("*.csv")):
        for r in _read(path):  # several runs on one day: the latest observation of the product wins
            k = (r["date"], r["shop"], r["product_id"])
            if k not in latest or r["scraped_at"] >= latest[k]["scraped_at"]:
                latest[k] = r
    # Exclusion rules apply to the stored history too, so a rule added later also cleans older runs.
    rows = [r for r in latest.values() if not EXCLUDE.search(f"{r.get('brand', '')} {r['name']}")]
    for r in rows:
        for k in ("price", "original_price", "discount_pct", "unit_price", "multibuy_price",
                  "lowest_30d", "liters", "price_per_l"):
            r[k] = float(r[k]) if r.get(k) not in ("", None) else None
        r["multibuy_qty"] = int(r["multibuy_qty"]) if r.get("multibuy_qty") else None
        for k in ("on_sale", "in_stock", "sponsored"):
            r[k] = r.get(k) == "1"
    return rows


BANNER_DIR = DATA_DIR / "banners"
BANNER_COLUMNS = ["date", "platform", "placement", "position", "title", "owner", "brand", "link", "image", "source"]
# Campaigns seen by a logged-in user (screenshots), which the anonymous scrape cannot see. Edited by hand.
MANUAL_BANNERS = "manual.csv"


def save_banners(rows, banner_dir=BANNER_DIR):
    banner_dir = Path(banner_dir)
    banner_dir.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for r in rows:
        by_month.setdefault(r["date"][:7], []).append(r)
    for month, new in by_month.items():
        path = banner_dir / f"{month}.csv"
        replaced = {(r["date"], r["platform"]) for r in new}
        old = [r for r in _read(path) if (r["date"], r["platform"]) not in replaced]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=BANNER_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(old + new)


def load_banners(banner_dir=BANNER_DIR):
    rows = []
    for path in sorted(Path(banner_dir).glob("*.csv")):
        rows.extend(_read(path))
    return rows


COVERAGE_DIR = DATA_DIR / "coverage"
COVERAGE_COLUMNS = ["date", "scraped_at", "platform", "store", "scope", "status", "checked", "failed",
                    "products", "note", "area", "login", "method"]
SEARCH_DIR = DATA_DIR / "search"


def save_coverage(rows, coverage_dir=COVERAGE_DIR):
    return _append(rows, coverage_dir, COVERAGE_COLUMNS, ("scraped_at", "platform", "store", "scope"))


def load_coverage(coverage_dir=COVERAGE_DIR):
    rows = [r for path in sorted(Path(coverage_dir).glob("*.csv")) for r in _read(path)]
    for r in rows:  # older runs stored "ok" for a store with nothing to check
        if r.get("checked") in ("0", 0):
            r["status"] = "failed"
    return rows


def save_search(rows, search_dir=SEARCH_DIR):
    from .search import COLUMNS
    return _append(rows, search_dir, COLUMNS, ("scraped_at", "platform", "store", "query", "position"))


def load_search(search_dir=SEARCH_DIR):
    return [r for path in sorted(Path(search_dir).glob("*.csv")) for r in _read(path)]
