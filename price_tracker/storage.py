"""Append-only price history stored as monthly CSV files (git friendly).

data/history/YYYY-MM.csv — one row per (date, shop, product_id). Re-running a
scrape on the same day replaces that day's rows for the shop.
"""

import csv
from pathlib import Path

from .models import Observation

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_DIR = DATA_DIR / "history"


def save(observations, history_dir=HISTORY_DIR):
    history_dir = Path(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for o in observations:
        by_month.setdefault(o.date[:7], []).append(o)
    cols = Observation.columns()
    for month, obs in by_month.items():
        path = history_dir / f"{month}.csv"
        replaced = {(o.date, o.shop) for o in obs}
        rows = [r for r in _read(path) if (r["date"], r["shop"]) not in replaced]
        rows += [o.as_row() for o in obs]
        rows.sort(key=lambda r: (r["date"], r["shop"], r["owner"], r["brand"], r["name"]))
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    return sum(len(v) for v in by_month.values())


def _read(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(history_dir=HISTORY_DIR):
    """All rows from all months, numeric fields converted."""
    rows = []
    for path in sorted(Path(history_dir).glob("*.csv")):
        rows.extend(_read(path))
    for r in rows:
        for k in ("price", "original_price", "discount_pct", "unit_price"):
            r[k] = float(r[k]) if r.get(k) not in ("", None) else None
        for k in ("on_sale", "in_stock"):
            r[k] = r.get(k) == "1"
    return rows
