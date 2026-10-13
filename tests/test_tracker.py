"""Offline tests. Payloads mirror the shapes of the shops' JSON APIs."""

import tempfile
import unittest

from price_tracker import report, storage
from price_tracker.kosik import Kosik
from price_tracker.portfolio import classify
from price_tracker.rohlik import Rohlik

D, TS = "2026-10-13", "2026-10-13T06:00:00+00:00"


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get_json(self, path, params=None):
        self.calls.append((path, params))
        handler = self.routes[path]
        return handler(params) if callable(handler) else handler


ROHLIK_CARDS = {
    1: {"productId": 1, "name": "Coca-Cola Zero", "brand": "Coca-Cola", "slug": "coca-cola-zero",
        "textualAmount": "1,5 l", "unit": "l",
        "prices": {"originalPrice": 44.9, "salePrice": 32.9, "unitPrice": 21.93,
                   "saleValidTill": "2026-10-19T23:59:00+02:00", "currency": "CZK"},
        "stock": {"availabilityStatus": "AVAILABLE"}},
    2: {"productId": 2, "name": "Pepsi Max", "brand": None, "textualAmount": "6 x 330 ml", "unit": "l",
        "prices": {"originalPrice": 99.9, "salePrice": None, "unitPrice": 50.45, "currency": "CZK"},
        "stock": {"availabilityStatus": "SOLD_OUT"}},
    3: {"productId": 3, "name": "Kofola Original", "brand": "Kofola", "textualAmount": "2 l",
        "prices": {"originalPrice": 39.9, "salePrice": None}},
}


def rohlik_fake():
    def names(params):
        ids = [v for k, v in params if k == "categories"]
        table = {10: "Nápoje", 11: "Ovoce a zelenina", 20: "Limonády", 21: "Alkohol", 30: "Colové"}
        return [{"categoryId": i, "name": table[i]} for i in ids]

    def cards(params):
        return [ROHLIK_CARDS[v] for k, v in params if k == "products"]

    return FakeHttp({
        "/api/v1/categories/normal/subcategories": {"categoryIds": [10, 11]},
        "/api/v1/categories/normal/10/subcategories": {"categoryIds": [20, 21]},
        "/api/v1/categories/normal/20/subcategories": {"categoryIds": [30]},
        "/api/v1/categories/normal/30/subcategories": {"categoryIds": []},
        "/api/v1/categories": names,
        "/api/v1/categories/normal/30/products": {"productIds": [1, 2, 3]},
        "/api/v1/products/card": cards,
        "/api/v1/products/prices": [
            {"productId": 1, "sales": [
                {"type": "sale", "triggerAmount": 1, "price": {"amount": 32.9}, "active": True,
                 "validTill": "2026-10-19T23:59:00+02:00"}]},
            {"productId": 2, "sales": [
                {"type": "premium", "triggerAmount": 1, "price": {"amount": 89.9}, "active": True},
                {"type": "multipack", "triggerAmount": 2, "price": {"amount": 84.9}, "active": True}]}],
    })


KOSIK_MENU = {"categories": [
    {"name": "Nápoje", "url": "/c1-napoje", "subcategories": [
        {"name": "Limonády", "url": "/c2-limonady"},
        {"name": "Pivo", "url": "/c3-pivo"}]},
    {"name": "Pečivo", "url": "/c9-pecivo"}]}


def kosik_fake():
    page1 = {"products": {"totalCount": 3, "cursor": "abc", "items": [
        {"id": 501, "name": "Fanta Pomeranč 1,5 l", "url": "/p501-fanta", "price": 29.9,
         "recommendedPrice": 39.9, "percentageDiscount": 25, "actionLabel": "Akce platí do 27. 10.",
         "brand": {"id": 1, "name": "Fanta"}, "cumulativePrices": [],
         "productQuantity": {"prefix": "", "value": 1.5, "unit": "l"},
         "pricePerUnit": {"price": 19.93, "unit": "l"}}]}}
    page2 = {"cursor": None, "products": [
        {"id": 502, "name": "Coca-Cola", "url": "/p502-coca-cola", "price": 44.9,
         "recommendedPrice": 44.9, "percentageDiscount": 0, "brand": None,
         "cumulativePrices": [{"quantity": 2, "price": 36.9, "percentageDiscount": 17}]},
        {"id": 503, "name": "Mattoni Grep", "url": "/p503", "price": 19.9,
         "brand": {"name": "Mattoni"}}]}
    http = FakeHttp({
        "/api/front/menu/main": KOSIK_MENU,
        "/api/front/page/products": page1,
    })
    http.post_json = lambda path, body: (http.calls.append((path, body)), page2)[1]
    return http


class PortfolioTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify("Coca-Cola Zero Cherry 0,5 l"), ("Coca-Cola", "Coca-Cola"))
        self.assertEqual(classify("Pepsi Max 1,5l"), ("PepsiCo", "Pepsi"))
        self.assertEqual(classify("7 UP Free"), ("PepsiCo", "7UP"))
        self.assertEqual(classify("Lipton Ice Tea Peach"), ("PepsiCo", "Lipton Ice Tea"))
        self.assertEqual(classify("Natura jemně perlivá"), ("Coca-Cola", "Natura"))
        self.assertIsNone(classify("Lipton Yellow Label čaj"))
        self.assertIsNone(classify("Natural džus"))
        self.assertIsNone(classify("Kofola Original"))
        self.assertIsNone(classify("Sodastream příchuť Pepsi"))
        self.assertIsNone(classify("Capri-Sun Monster Alarm"))


class RohlikTest(unittest.TestCase):
    def test_scrape(self):
        http = rohlik_fake()
        obs = {o.product_id: o for o in Rohlik(http).scrape(D, TS)}
        self.assertEqual(set(obs), {"1", "2"})
        coke = obs["1"]
        self.assertTrue(coke.on_sale)
        self.assertEqual((coke.price, coke.original_price, coke.discount_pct), (32.9, 44.9, 26.7))
        self.assertIn('"sale"', coke.promo_info)
        self.assertEqual(coke.url, "https://www.rohlik.cz/1-coca-cola-zero")
        pepsi = obs["2"]
        self.assertFalse(pepsi.on_sale)
        self.assertFalse(pepsi.in_stock)
        self.assertEqual(pepsi.price, 99.9)  # Xtra-only "premium" price is ignored
        self.assertEqual((pepsi.multibuy_qty, pepsi.multibuy_price), (2, 84.9))
        self.assertEqual(coke.sale_valid_till, "2026-10-19T23:59:00+02:00")
        self.assertNotIn("/api/v1/categories/normal/21/subcategories", [c[0] for c in http.calls])


class KosikTest(unittest.TestCase):
    def test_scrape(self):
        http = kosik_fake()
        obs = {o.product_id: o for o in Kosik(http).scrape(D, TS)}
        self.assertEqual(set(obs), {"501", "502"})
        self.assertEqual(http.calls[1], ("/api/front/page/products", {"slug": "c2-limonady", "limit": 30}))
        fanta = obs["501"]
        self.assertTrue(fanta.on_sale)
        self.assertEqual((fanta.price, fanta.original_price, fanta.discount_pct), (29.9, 39.9, 25))
        self.assertEqual(fanta.amount, "1,5 l")
        self.assertEqual(fanta.url, "https://www.kosik.cz/p501-fanta")
        self.assertEqual(fanta.sale_valid_till, "2026-10-27")
        self.assertIn(("/api/front/products/more", {"cursor": "abc", "limit": 30}), http.calls)
        coke = obs["502"]
        self.assertFalse(coke.on_sale)
        self.assertEqual((coke.price, coke.multibuy_qty, coke.multibuy_price), (44.9, 2, 36.9))


class StorageReportTest(unittest.TestCase):
    def test_history_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            day1 = Rohlik(rohlik_fake()).scrape("2026-10-12", TS)
            for o in day1:
                if o.product_id == "1":  # not on sale the day before
                    o.price, o.on_sale, o.discount_pct = 44.9, False, None
            storage.save(day1, tmp)
            storage.save(Rohlik(rohlik_fake()).scrape(D, TS), tmp)
            storage.save(Rohlik(rohlik_fake()).scrape(D, TS), tmp)  # same-day rerun replaces
            rows = storage.load(tmp)
            self.assertEqual(len(rows), 4)

            changes = report.price_changes(rows, D)
            self.assertEqual([(p["price"], c["price"]) for p, c in changes], [(44.9, 32.9)])
            md = report.markdown(rows)
            self.assertIn("Aktuální slevy (1)", md)
            self.assertIn("Coca-Cola Zero", md)
            html = report.dashboard(rows)
            self.assertIn('"Coca-Cola Zero"', html)
            self.assertNotIn("/*DATA*/", html)


if __name__ == "__main__":
    unittest.main()
