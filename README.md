# F-liiga Value Model v0.5

GitHub-valmis miesten F-liigan maalimäärä- ja 1X2-todennäköisyyksien arviointiin.
Malli sovittaa ottelutuloksiin joukkuekohtaiset hyökkäys- ja puolustusvahvuudet,
kotiedun sekä antaa tuoreemmille otteluille enemmän painoa. Totals-jakaumassa
käytetään aineistosta estimoitua negatiivisen binomijakauman ylidispersiota.
Malli tuottaa odotetut maalit, over/under- ja 1X2-todennäköisyydet, reilut
kertoimet, markkinan marginaalittomat todennäköisyydet sekä EV:n.

> Tämä on tutkimus- ja päätöksenteon apuväline, ei tae voitollisesta vedonlyönnistä.

Katso aineisto, validointitulokset ja tunnetut rajoitukset tiedostosta
[`MODEL_CARD.md`](MODEL_CARD.md). Tarkat walk-forward-tulokset ovat tiedostossa
[`BACKTEST_REPORT.md`](BACKTEST_REPORT.md), ja lähteiden kattavuus tiedostossa
[`DATA_SOURCES.md`](DATA_SOURCES.md).

## Ominaisuudet

- automaattinen miesten F-liigan ottelukerääjä julkisesta F-liiga-rajapinnasta
- mukana 20.9.2020 alkaen kerätty historiadata
- regularisoitu, tuoreuspainotettu joukkuekohtainen Poisson-malli
- totals-ylidispersio negatiivisella binomijakaumalla
- over/under-todennäköisyydet, reilut kertoimet ja push-tuki
- 1X2-tulosjakauma 60 minuutin tulokselle
- suhteellinen marginaalin poisto vedonvälittäjän kertoimista
- reilu kerroin, markkinaero, EV ja murto-Kelly
- aikajärjestyksessä tehtävä walk-forward-backtest
- selainkäyttöliittymä Streamlitillä
- komentorivityökalu automaatiota varten
- testit ja esimerkkidata
- aikaleimattu SQLite-kerroinhistoria usealle vedonvälittäjälle
- päivän parhaiden totals-kertoimien value-lista
- vetoloki ja päätöskertoimeen perustuva CLV-seuranta
- maksuton ajastus GitHub Actionsilla

## Helpoin käynnistys

### Windows

1. Lataa projekti GitHubista valitsemalla **Code → Download ZIP**.
2. Pura ZIP-paketti.
3. Kaksoisklikkaa tiedostoa **`KAYNNISTA_WINDOWS.bat`**.

Ensimmäinen käynnistys asentaa tarvittavat paketit automaattisesti. Seuraavilla
kerroilla kaksoisklikkaa samaa tiedostoa. Tarvitset Python 3.11:n tai uudemman.

### macOS ja Linux

```bash
chmod +x kaynnista_mac_linux.sh
./kaynnista_mac_linux.sh
```

Käyttöliittymässä tuleva ottelu valitaan suoraan listasta. Neljän vedonvälittäjän
kertoimet voi liittää samaan taulukkoon kerralla, minkä jälkeen ohjelma järjestää
Over- ja Under-vaihtoehdot odotusarvon mukaan.

## Kehittäjän asennus

```bash
git clone <oman-reposi-url>
cd fliiga-value-model
python -m venv .venv
```

Aktivoi ympäristö ja asenna projekti:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -e ".[app,dev]"
```

## Selainkäyttöliittymä

```bash
streamlit run app.py
```

Sovellus käyttää oletuksena mukana tulevaa oikeaa F-liiga-historiadataa. Valitse
joukkueet, syötä vedonvälittäjän totals-raja ja over/under-kertoimet. Sovellus
laskee todennäköisyydet, reilut kertoimet ja EV:n. Oman historian ja usean
ottelun kerrointiedoston voi ladata CSV:nä.

## Päivitä F-liiga-data

```bash
fliiga-model collect \
  --games-output data/fliiga_men_history.csv \
  --fixtures-output data/fliiga_men_fixtures.csv
```

Kerääjä lukee F-liigan julkista WordPress REST -rajapintaa maltillisella
kutsutahdilla. Lähteen rakennetta ei ole luvattu pysyväksi, joten integraatiotesti
ilmoittaa selkeästi, jos F-liiga muuttaa kenttiä.

## Komentorivi

### 1. Tuo kertoimet usealta vedonvälittäjältä

Kopioi `data/odds_template.csv`, lisää jokainen over/under-havainto omalle rivilleen
ja säilytä `bookmaker`-sarakkeessa lähde. Samassa tiedostossa voi olla rajaton määrä
vedonvälittäjiä. Vie CSV OddsHubista tai täytä se käyttämiesi sivujen näkyvillä
kertoimilla. Tämän jälkeen:

```bash
fliiga-model odds-import --input omat_kertoimet.csv --db data/odds.db
```

Jokainen tuonti saa aikaleiman. Jos CSV sisältää `collected_at`-sarakkeen, sen
aikaleimaa käytetään. Tämä mahdollistaa avaus-, väli- ja päätöskertoimien säilyttämisen.

### 2. Tee päivän value-lista

```bash
fliiga-model value-report \
  --db data/odds.db \
  --games data/fliiga_men_history.csv \
  --fixtures data/fliiga_men_fixtures.csv \
  --min-ev 0.05 \
  --output data/daily_value.csv
```

Raportti valitsee jokaiselle ottelulle, rajalle ja puolelle parhaan tarjolla olevan
kertoimen. `ev` on mallin odotusarvo per panosyksikkö ja `kelly_20pct` varovainen
panososuus pelikassasta. Se ei huomioi vetokohtaisia panosrajoja.

### 3. Kirjaa veto

```bash
fliiga-model record-bet --db data/odds.db \
  --bookmaker Coolbet --event-start 2026-09-20T17:00:00+03:00 \
  --home-team "Nokian KrP" --away-team LASB \
  --line 10.5 --side over --odds 2.05 --stake 10
```

### 4. Laske CLV

```bash
fliiga-model clv-report --db data/odds.db --output data/clv_report.csv
```

CLV lasketaan saman vedonvälittäjän viimeisestä ennen ottelun alkua tallennetusta
saman rajan kertoimesta: `saatu kerroin / päätöskerroin - 1`. Positiivinen arvo
tarkoittaa, että sait päätösmarkkinaa paremman hinnan. Päätöskerroin syntyy vasta,
kun tuot uuden kerroshavainnon lähellä ottelun alkua.

### Maksuton päivittäinen ajo

`.github/workflows/daily.yml` päivittää F-liiga-datan ja muodostaa raportit joka
aamu sekä käsin käynnistettäessä. GitHub Actions tallentaa tulokset ladattavaksi
artifactiksi. Lisää halutessasi ajon lähtötiedostoksi `data/odds_input.csv`.

Vedonvälittäjien sivut ja kirjautumiset muuttuvat usein. Projekti ei kierrä
CAPTCHAa tai bottisuojausta. Maksuton ja vakaa oletuspolku on CSV-tuonti; sen voi
korvata myöhemmin virallisella API-adapterilla ilman tietokannan tai mallin muutosta.

### Muut komennot

Ennusteet:

```bash
fliiga-model predict \
  --games data/games_sample.csv \
  --fixtures data/fixtures_sample.csv \
  --output predictions.csv
```

Backtest:

```bash
fliiga-model backtest \
  --games oma_historiadata.csv \
  --min-train-games 250 \
  --output backtest_results.csv
```

Oikea totals-ROI-backtest historiallisilla kertoimilla:

```bash
fliiga-model totals-backtest \
  --games data/fliiga_men_history.csv \
  --odds historialliset_kertoimet.csv \
  --min-train-games 250 \
  --min-ev 0.05 \
  --output totals_backtest.csv
```

Rajaa tulos halutessasi yhteen yhtiöön esimerkiksi `--bookmaker Coolbet`.
Testi käyttää vain ennen kutakin ottelua pelattuja tuloksia ja vain ennen
alkamisaikaa kerättyjä kertoimia. Se valitsee korkeintaan yhden, suurimman EV:n
vedon ottelua kohti ja raportoi tasapanos-ROI:n.

## CSV-rakenne

`games.csv` tarvitsee sarakkeet:

```text
date,home_team,away_team,home_goals,away_goals
```

Historiadataan voi lisätä päätöskertoimet:

```text
home_odds,draw_odds,away_odds
```

`fixtures.csv` tarvitsee sarakkeet:

```text
date,home_team,away_team
```

EV-laskentaa varten lisää myös:

```text
home_odds,draw_odds,away_odds
```

Totals-arvioita varten käytä sarakkeita:

```text
total_line,over_odds,under_odds
```

Kerroinhistorian CSV-rakenne on tiedostossa `data/odds_template.csv`:

```text
collected_at,bookmaker,event_id,event_start,home_team,away_team,total_line,side,decimal_odds,source_url
```

Käytä aina 60 minuutin 1X2-kertoimia, koska nykyinen malli ennustaa varsinaisen
peliajan tulosta. Älä sekoita mukaan jatkoajan sisältäviä moneyline-kertoimia.

## Mallin rajat ja seuraavat kehitysaskeleet

Nykyinen versio on tarkoituksella auditoitava baseline. Ennen oikeaa käyttöä:

1. kerää historialliset totals-kertoimet usealta vedonvälittäjältä
2. tallenna sekä avaus- että päätöskertoimet aikaleimoineen
3. erottele runkosarja ja pudotuspelit täydellisesti
4. lisää kokoonpano-, maalivahti-, lepo- ja mahdollinen laukaustieto
5. kalibroi todennäköisyydet vain erillisellä validointijaksolla
6. seuraa ROI:n lisäksi log lossia, Brier scorea ja closing line valuea

## Testit

```bash
pytest
ruff check .
```
