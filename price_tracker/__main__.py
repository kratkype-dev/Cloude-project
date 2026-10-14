"""CLI: python -m price_tracker {scrape,sample,report}"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import report, storage
from .bolt import Bolt
from .kosik import Kosik
from .rohlik import Rohlik
from .wolt import Wolt

SHOPS = {"rohlik": Rohlik, "kosik": Kosik, "wolt": Wolt, "bolt": Bolt}


def run_scrape(shops):
    now = datetime.now(timezone.utc)
    date = now.astimezone(ZoneInfo("Europe/Prague")).date().isoformat()
    scraped_at = now.isoformat(timespec="seconds")
    results, banners, failed = {}, [], []
    for name in shops:
        try:
            shop = SHOPS[name]()
            results[name] = shop.scrape(date, scraped_at)
            logging.info("%s: %d portfolio products", name, len(results[name]))
        except Exception:
            logging.exception("%s: scrape failed", name)
            failed.append(name)
            continue
        if hasattr(shop, "banners"):
            try:
                banners += shop.banners(date)
            except Exception:
                logging.exception("%s: banners failed", name)
    return results, banners, failed


def print_sample(observations):
    for o in sorted(observations, key=lambda o: (o.shop, o.owner, o.brand, o.name)):
        sale = f"  SLEVA -{o.discount_pct}% (běžně {o.original_price})" if o.on_sale else ""
        if o.multibuy_qty:
            sale += f"  od {o.multibuy_qty} ks {o.multibuy_price}/ks"
        print(f"{o.shop:7} {o.store[:16]:16} {o.owner:10} {o.brand:14} {o.name[:45]:45} {o.amount:>12} "
              f"{o.price!s:>8} Kč{sale}")


def write_reports():
    rows = storage.load()
    (storage.DATA_DIR / "report.md").write_text(report.markdown(rows), encoding="utf-8")
    (storage.DATA_DIR / "dashboard.html").write_text(
        report.dashboard(rows, storage.load_banners()), encoding="utf-8")
    logging.info("Reports written to %s", storage.DATA_DIR)


def main(argv=None):
    p = argparse.ArgumentParser(prog="price_tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd, help_ in (("scrape", "scrape and append to data/history"),
                       ("sample", "scrape and print, without saving")):
        s = sub.add_parser(cmd, help=help_)
        s.add_argument("--shop", choices=list(SHOPS), action="append",
                       help="limit to a shop (repeatable); default: all")
    sub.add_parser("report", help="regenerate data/report.md and data/dashboard.html")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "report":
        write_reports()
        return 0
    results, banners, failed = run_scrape(args.shop or list(SHOPS))
    observations = [o for obs in results.values() for o in obs]
    if args.cmd == "sample":
        print_sample(observations)
    else:
        storage.save(observations)
        storage.save_banners(banners)
        write_reports()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
