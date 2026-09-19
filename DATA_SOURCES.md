# Data sources and bookmaker coverage

## Included match data

Completed matches and fixtures come from the public F-liiga WordPress REST API
used by the official match pages: <https://fliiga.com/ottelut/miehet/>.
The bundled snapshot must be refreshed with `fliiga-model collect` before use.

## Odds data

No bookmaker odds are redistributed with this repository. Import only data that
you are permitted to use with `fliiga-model odds-import` or
`fliiga-model totals-backtest`.

The normalized format supports Coolbet, Unibet, bet365, Paf and other books via
the `bookmaker` column. There is currently no stable, unauthenticated public API
for the four named bookmakers that provides full historical F-liiga totals.

OddsPortal publicly displays F-liiga results back to 2007/08 and some match-level
over/under closing prices. It is not integrated: its terms restrict copying,
downloading and reuse of site content without written permission.

- F-liiga: <https://fliiga.com/ottelut/miehet/>
- OddsPortal F-liiga archive: <https://www.oddsportal.com/floorball/finland/f-liiga/results/>
- OddsPortal terms: <https://www.oddsportal.com/terms/>

## Recommended collection schedule

For a prospective, auditable dataset, save every offered line and both sides:

- opening observation when the market appears
- 24 hours before scheduled start
- 6 hours before scheduled start
- 1 hour before scheduled start
- final observation before scheduled start

Never mix regulation-only and overtime-inclusive markets. Store the source URL,
bookmaker, collection timestamp, scheduled start, teams, line, side and decimal
odds for every observation.
