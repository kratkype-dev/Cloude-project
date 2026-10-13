# Cloude-project — sledování cen Coca-Cola a PepsiCo

Každý den stahuje ceny nápojů z portfolia **The Coca-Cola Company** a **PepsiCo**
z **rohlik.cz** a **kosik.cz**. Ukládá běžnou cenu, aktuální cenu, **slevy**
(procento a platnost) a cenu za litr. Z historie se pak dá sledovat, jak se ceny
mění v čase a jak často jsou produkty v akci.

## Jak to funguje

Neparsuje se HTML. Oba e-shopy mají interní JSON API, ze kterého se vykresluje
jejich web, a scraper ho volá přímo. Je to stabilnější a rychlejší než
parsovat HTML a nepotřebuje se přihlašovat.

| | Rohlík | Košík |
|---|---|---|
| Strom kategorií | `/api/v1/categories/normal/{id}/subcategories` | `/api/front/menu/main` |
| Výpis produktů | `/api/v1/categories/normal/{id}/products?page=&size=50` | `/api/front/page/products?slug=…&limit=30` (+ odkaz `more`) |
| Ceny | `/api/v1/products/card` → `originalPrice`, `salePrice`, `saleValidTill`, `unitPrice` | `price`, `recommendedPrice`, `percentageDiscount`, `pricePerUnit` |
| Typ akce | `/api/v1/products/prices` → `sales[].type` (sleva, multipack…) | uloží se, pokud jsou v položce štítky nebo akce |

Postup: najde se kategorie **Nápoje**, projdou se všechny její podkategorie
(alkohol, pivo, víno a káva se přeskakují), stáhnou se všechny produkty a ponechají
se jen ty, které patří do portfolia. Seznam značek je v
[`price_tracker/portfolio.py`](price_tracker/portfolio.py):

- **Coca-Cola:** Coca-Cola, Fanta, Sprite, Kinley, Schweppes, Fuze Tea, Cappy, Natura, Römerquelle, Powerade, Monster, Burn, Costa Coffee, Smartwater, BonAqua
- **PepsiCo:** Pepsi, 7UP, Mirinda, Mountain Dew, Lipton Ice Tea, Rockstar, Gatorade

## Použití

Stačí Python 3.10 nebo novější a jen standardní knihovna.

```bash
python -m price_tracker sample                 # zkušební vzorek: vypíše produkty a slevy, nic neukládá
python -m price_tracker sample --shop kosik    # jen jeden obchod
python -m price_tracker scrape                 # stáhne data a přidá je do historie, přegeneruje reporty
python -m price_tracker report                 # jen přegeneruje reporty z historie
python -m unittest discover -s tests -t .      # offline testy
```

## Data

- `data/history/YYYY-MM.csv`: historie, jeden řádek na produkt, obchod a den.
  Když se scrape pustí víckrát za den, data z toho dne se přepíšou.
  Sloupce: `date, shop, product_id, name, owner, brand, amount, price, original_price,
  on_sale, discount_pct, sale_valid_till, unit_price, unit, in_stock, url, promo_info`.
- `data/report.md`: přehled posledního měření, aktuální slevy, změny cen proti
  předchozímu dni, průměrná cena za litr podle značky a obchodu a historie každého
  produktu (min, max, kolik dní byl ve slevě).
- `data/dashboard.html`: interaktivní graf vývoje ceny a běžné ceny pro každý produkt
  (body ve slevě jsou červeně) a filtry podle obchodu, vlastníka, značky a slev.

## Pravidelné spouštění

Workflow [`.github/workflows/scrape-prices.yml`](.github/workflows/scrape-prices.yml)
se spouští každý den v 07:17 pražského času (ručně jde spustit přes *Run workflow*).
Data commitne zpátky do repozitáře, takže historie je v gitu.

Pokud GitHub runnery e-shopy blokují (běží na IP adresách v USA), stačí spouštět
scrape z vlastního stroje přes cron:

```cron
17 7 * * * cd /cesta/Cloude-project && python3 -m price_tracker scrape && git add data && git commit -qm "data: prices" && git push -q
```

## Na co dát pozor

- **Ceny závisí na doručovací adrese.** Anonymní požadavek dostane výchozí
  sortiment (Praha). Pro jinou lokalitu by bylo potřeba poslat session cookie.
- **Neoficiální API.** Endpointy se můžou změnit. Když scrape spadne, workflow
  skončí červeně a data z obchodu, který prošel, se i tak uloží.
- **Slevy:** `on_sale` znamená, že platí akční cena (u Rohlíku `salePrice`,
  u Košíku `percentageDiscount` > 0). Multipackové a množstevní akce
  („2+1“, „od 2 ks“) se nepromítnou do `price`. Jsou jen ve sloupci `promo_info`.
- Scraper je ohleduplný: mezi požadavky čeká zhruba 0,7 s a jede jednou denně.
  Je dobré respektovat obchodní podmínky obou e-shopů.
