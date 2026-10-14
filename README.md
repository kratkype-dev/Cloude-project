# Nápojový radar — ceny, slevy a kampaně nápojů

Každý den stahuje ceny nápojů z portfolia **The Coca-Cola Company** a **PepsiCo**
z **rohlik.cz** a **kosik.cz**. Ukládá běžnou cenu, aktuální cenu, **slevy**
(procento a platnost) a cenu za litr. Z historie se pak dá sledovat, jak se ceny
mění v čase a jak často jsou produkty v akci.

## Co sleduje

**Firmy a značky** (`price_tracker/portfolio.py`):

- **Coca-Cola:** Coca-Cola, Fanta, Sprite, Kinley, Fuze Tea, Cappy, Natura, Römerquelle, Powerade, Monster, Burn, Costa Coffee, Smartwater, BonAqua
- **PepsiCo:** Pepsi, 7UP, Mirinda, Mountain Dew, Lipton Ice Tea, Rockstar, Gatorade (v ČR je plní a distribuuje Mattoni 1873)
- **Kofola:** Kofola, Citro Cola, Rajec, Korunní, Ondrášovka, Kláštorná, Šaratica, Vinea, Top Topic, Jupí, Jupík, Semtex, UGO
- **Mattoni:** Mattoni, Magnesia, Aquila, Poděbradka, Dobrá voda, Hanácká kyselka, Schweppes
- **Red Bull:** Red Bull

**Kanály** (Praha, anonymní zákazník, doručení na náměstí Míru):

| Kanál | Zdroj dat | Bannery a reklama |
|---|---|---|
| Rohlík | interní API, kategorie Nápoje | sponzorované produkty v kategoriích |
| Košík | interní API, kategorie Nápoje | bannery v kategoriích Nápoje |
| Wolt | assortment API prodejen Tesco Národní, Albert Vinohradská, PENNY Vyšehrad, Žabka Římská | hlavní karusel úvodní stránky, sponzorované produkty |
| Bolt Food | veřejné API, vyhledávání značek v Tesco Národní a Žabka Legerova | jen pro přihlášené, neměří se |
| foodora | chráněno proti automatickému sběru (PerimeterX), neměří se | – |

U každého produktu se ukládá běžná cena, aktuální cena, typ akce (sleva, dlouhodobá, množstevní), platnost akce,
cena za litr, EAN (Wolt), nejnižší cena za 30 dní (Wolt), sponzorované umístění a dostupnost.

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
- `data/banners/YYYY-MM.csv`: bannery a placená umístění.
- `data/dashboard.html`: **Nápojový radar**, nástroj pro key account tým. Souhrn v běžné řeči, slevy a akce,
  srovnání cen napříč kanály, vývoj v čase, kampaně a vyhledávání s detailem produktu.

## Pravidelné spouštění a veřejná stránka

Workflow [`.github/workflows/scrape-prices.yml`](.github/workflows/scrape-prices.yml) běží každé pondělí
v 7:17 (ručně přes **Actions → Nápojový radar – týdenní měření → Run workflow**). Stáhne data, uloží je do
repozitáře a zveřejní dashboard na GitHub Pages: `https://kratkype-dev.github.io/Cloude-project/`.

Jednorázové nastavení: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
Workflow se spouští jen z hlavní větve (`main`).

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
