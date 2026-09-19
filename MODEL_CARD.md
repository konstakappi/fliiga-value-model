# Model card – F-liiga Value Model 0.5.1

## Käyttötarkoitus

Malli arvioi miesten F-liigan otteluiden varsinaisen peliajan maalimääriä ja
1X2-todennäköisyyksiä. Ensisijainen markkina on ottelun kokonaismaalimäärä.
Mallia ei pidä käyttää automaattisena vedonlyöntibottina tai voiton takeena.

## Data

- lähde: F-liigan julkinen WordPress REST -rajapinta
- 1 440 pelattua miesten ottelua
- kaudet 2020–21–2026–27
- datan tilanne: 19.9.2026
- 12 pelaamatta jäänyttä 0–0-pudotuspelivarausta poistettu
- mukana oleva `fliiga_men_fixtures.csv`: 159 tulevaa ottelua

Historiallisia vedonlyöntikertoimia ei toimiteta valmiina. Versio 0.3 tallentaa
käyttäjän tuomat kerroshavainnot SQLiteen, muodostaa value-listan ja laskee CLV:n,
kun samasta kohteesta on tallennettu päätöskerroin.

## Malli

- joukkuekohtaiset hyökkäys- ja puolustusparametrit
- erillinen kotietu
- L2-regularisointi pienille otoksille
- eksponentiaalinen tuoreuspainotus, oletuspuoliintumisaika 120 päivää
- 1X2-jakauma riippumattomista Poisson-maaleista
- totals-jakauma Poissonista tai negatiivisesta binomijakaumasta aineistosta
  estimoidun ylidispersion mukaan

## Walk-forward-validointi

Validointi tehtiin aikajärjestyksessä 250 ensimmäisen ottelun jälkeen. Malli
sovitettiin uudelleen 50 ottelun välein, eikä tulevia otteluita käytetty
ennusteissa.

| Mittari | Tulos |
|---|---:|
| Testiottelut | 1 170 |
| 1X2 log loss | 0,6124 |
| 1X2 Brier score | 0,3563 |
| Totals MAE | 2,683 maalia |
| Totals RMSE | 3,361 maalia |
| Laajenevan liigakeskiarvon MAE | 2,793 maalia |
| Laajenevan liigakeskiarvon RMSE | 3,528 maalia |

Malli voitti yksinkertaisen liigakeskiarvobaselinen maalimäärävirheessä, mutta
tämä ei vielä osoita vedonlyöntietua.

## Tunnetut rajoitukset

- mukana ei ole valmista historiallista avaus- tai päätöskerroinaineistoa
- ei varmistettuja kokoonpanoja tai aloittavia maalivahteja
- ei lepo-, matkustus-, laukaus- tai tyhjän maalin tietoja
- nousijajoukkueista on kauden alussa erittäin vähän dataa
- runkosarjan ja pudotuspelien erot ovat lähdedatassa osittain epätäydellisiä
- julkisen rajapinnan kentät voivat muuttua ilman ennakkoilmoitusta

## Seuraava validointivaatimus

Kerää vähintään yksi kokonainen kausi aikaleimallista totals-kerroinhistoriaa:
vedonvälittäjä, ottelu, raja, over/under-kertoimet sekä avaus- ja päätöshetki.
Arvioi vasta sen jälkeen kalibraatio, CLV, ROI, vetomäärä ja suurin tappioputki
täysin erillisellä testijaksolla. Positiivinen takautuva EV tai CLV ei yksin takaa
positiivista tulevaa tuottoa.
