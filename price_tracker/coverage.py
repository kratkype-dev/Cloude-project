"""What each run actually managed to check, so a missing product can be told apart from a page that did not load.

One row per platform, store and scope (ceny = product listing, vyhledavani = search ranking, bannery):
how many units (categories, search terms, queries) were checked, how many failed, and the measuring context.
"""

AREA = "Praha 2, náměstí Míru"
LOGIN = "anonymní"
METHOD = "API e-shopu"


def entry(platform, store, scope, checked, failed, products=None, note=""):
    """status: ok (all units loaded), partial (some failed), failed (nothing loaded)."""
    status = "failed" if checked and failed >= checked else "partial" if failed else "ok"
    return {"platform": platform, "store": store, "scope": scope, "status": status,
            "checked": checked, "failed": failed, "products": "" if products is None else products,
            "note": note[:200], "area": AREA, "login": LOGIN, "method": METHOD}


def failed(platform, scope, error):
    """The whole platform failed before it could report its own coverage."""
    return entry(platform, "", scope, 1, 1, note=f"{type(error).__name__}: {error}")
