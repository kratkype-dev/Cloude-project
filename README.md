# Nápojový radar — ceny, slevy a kampaně nápojů

Stahuje ceny nápojů z portfolia **The Coca-Cola Company** a **PepsiCo**
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

**Vyhledávání:** prvních 10 výsledků pro dotazy „cola“, „limonáda“, „energy drink“, „ledový čaj“, „voda“ a „tonic“
na Rohlíku, Košíku a ve 4 prodejnách na Woltu, včetně označení sponzorovaných výsledků (Rohlík, Wolt).
Bolt Food pořadí výsledků nevrací a Košík reklamu ve vyhledávání neoznačuje.

## Pravidla vyhodnocení

- **Změna ceny** se hlásí od ±3 % proti poslednímu srovnatelnému měření produktu. Zvlášť běžná cena, akční cena
  a množstevní cena. Skok nad 50 % je jen „podezření“ (spíš změna balení nebo chyba dat), dokud ho nepotvrdí další měření.
- **Výpadek skladu a vyřazení z nabídky** platí jako ověřené až po 2 měřeních po sobě. Jedno měření je „podezření“.
  Návrat do prodeje se hlásí zvlášť.
- **Nenačteno není vyřazeno.** Každé měření ukládá, co se opravdu načetlo (`data/coverage/`). Produkt chybějící
  v obchodě, který se nenačetl celý nebo jen zčásti, je „nelze ověřit“, nikdy „vyřazen“.
- **Novinka:** první výskyt je „poprvé zachycen“. Potvrzená novinka je produkt zachycený 2× po sobě v obchodě,
  který se měřil už předtím.
- **Cenový index** = naše srovnatelná cena / cena konkurence × 100, **konkurent = 100**. Nad 100 je Coca-Cola dražší.
  Počítá se pro každý souboj (stejné balení a varianta) a za pár a platformu jako medián.
- **Podíl na viditelnosti** = pozice v Top 10 obsazené firmou / (dotazy × 10 pozic) v daném měření.
  Není to tržní podíl.

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

- `data/history/YYYY-MM.csv`: historie, jeden řádek na produkt a měření. Data se jen přidávají, nikdy nepřepisují.
  Druhé měření ve stejný den přidá vlastní řádky (`scraped_at` je čas měření v UTC) a pro vyhodnocení se bere
  poslední pozorování produktu v daném dni. Uložení stejného měření podruhé nic nepřidá.
  Hlavní sloupce: `date, scraped_at, shop, store, product_id, name, owner, brand, amount, price, original_price,
  on_sale, discount_pct, sale_valid_till, promo_type, multibuy_qty, multibuy_price, unit_price, in_stock, url, ean`.
- `data/coverage/YYYY-MM.csv`: co se při každém měření načetlo za platformu, prodejnu a oblast (ceny, vyhledávání,
  bannery): stav `ok / partial / failed`, počet kontrolovaných a neúspěšných kategorií, počet produktů,
  doručovací adresa, přihlášení a způsob sběru.
- `data/search/YYYY-MM.csv`: Top 10 výsledků vyhledávání pro každý dotaz, s pozicí, značkou a příznakem sponzorování.
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
Workflow se spouští jen z hlavní větve (`main`). Po sloučení změny v `price_tracker/` (vzhled nebo logika dashboardu) se stránka sama znovu zveřejní ze stávajících dat, bez nového měření.

## Na co dát pozor

- **Ceny závisí na doručovací adrese.** Anonymní požadavek dostane výchozí
  sortiment (Praha). Pro jinou lokalitu by bylo potřeba poslat session cookie.
- **Neoficiální API.** Endpointy se můžou změnit. Když scrape spadne, workflow
  skončí červeně a data z obchodu, který prošel, se i tak uloží.
- **Slevy:** `on_sale` znamená, že platí akční cena (u Rohlíku `salePrice`,
  u Košíku `percentageDiscount` > 0). Multipackové a množstevní akce
  („2+1“, „od 2 ks“) se nepromítnou do `price`. Jsou jen ve sloupci `promo_info`.
- Scraper je ohleduplný: mezi požadavky čeká zhruba 0,7 s (Bolt 1,5 s) a jede jednou týdně.
  Je dobré respektovat obchodní podmínky obou e-shopů.
