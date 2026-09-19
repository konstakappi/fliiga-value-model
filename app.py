from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from fliiga_model.collector import FliigaCollector
from fliiga_model.data import load_fixtures, load_games
from fliiga_model.market import OddsDatabase
from fliiga_model.model import PoissonStrengthModel
from fliiga_model.odds import (
    expected_value_with_push,
    fair_odds_with_push,
    market_anchored_total_probabilities,
)
from fliiga_model.predict import predict_fixtures

ROOT = Path(__file__).parent
GAMES_PATH = ROOT / "data" / "fliiga_men_history.csv"
FIXTURES_PATH = ROOT / "data" / "fliiga_men_fixtures.csv"
ODDS_DB_PATH = ROOT / "data" / "odds.db"
BOOKMAKERS = ["Coolbet", "Unibet", "bet365", "Paf"]


def fixture_label(row: pd.Series) -> str:
    return f"{row['date']:%d.%m. klo %H:%M} — {row['home_team']} – {row['away_team']}"


def prediction_row(
    model: PoissonStrengthModel,
    date: pd.Timestamp,
    home_team: str,
    away_team: str,
    line: float,
    over_odds: float,
    under_odds: float,
) -> pd.Series:
    fixture = pd.DataFrame(
        [
            {
                "date": date,
                "home_team": home_team,
                "away_team": away_team,
                "total_line": line,
                "over_odds": over_odds,
                "under_odds": under_odds,
            }
        ]
    )
    return predict_fixtures(model, fixture).iloc[0]


st.set_page_config(page_title="F-liiga vedonlyöntiapuri", page_icon="🥅", layout="wide")
st.title("🥅 F-liiga vedonlyöntiapuri")
st.caption("Valitse ottelu, lisää näkyvät kertoimet ja vertaa niitä mallin arvioon.")

with st.sidebar:
    st.header("Kolme vaihetta")
    st.markdown("1. Valitse ottelu.\n2. Lisää kertoimet.\n3. Tarkista EV.")
    st.warning("Malli ei takaa voittoa. Tarkista aina kokoonpanot ja maalivahdit.")
    with st.expander("Mallin lisäasetukset"):
        half_life = st.slider("Puoliintumisaika (päivää)", 30, 365, 120)
        l2 = st.slider("Regularisointi", 0.0, 10.0, 1.0, 0.1)
        ev_limit = st.slider("Value-raja", 0.0, 0.25, 0.05, 0.01)

try:
    games = load_games(GAMES_PATH)
    fixtures = load_fixtures(FIXTURES_PATH)
    model = PoissonStrengthModel(half_life_days=half_life, l2=l2).fit(games)
except (OSError, RuntimeError, ValueError) as error:
    st.error(f"Mallia ei voitu käynnistää: {error}")
    st.stop()

now_in_finland = pd.Timestamp.now(tz="Europe/Helsinki").tz_localize(None)
upcoming = fixtures[fixtures["date"] > now_in_finland].copy()
upcoming = upcoming[
    upcoming["home_team"].isin(model.team_index)
    & upcoming["away_team"].isin(model.team_index)
]
upcoming = upcoming.sort_values("date").reset_index(drop=True)

if upcoming.empty:
    st.error("Tulevia otteluita ei löytynyt. Päivitä data Data-välilehdeltä.")
    st.stop()

labels = {fixture_label(row): index for index, row in upcoming.iterrows()}
league_total_prior = float((games.tail(250)["home_goals"] + games.tail(250)["away_goals"]).mean())

calculator_tab, compare_tab, bets_tab, data_tab = st.tabs(
    ["🎯 Pikalaskuri", "⚖️ Vertaa vedonvälittäjiä", "🧾 Vedot ja CLV", "🔄 Data"]
)

with calculator_tab:
    st.subheader("Yhden kohteen pikalaskuri")
    selected_label = st.selectbox("Ottelu", list(labels), key="single_fixture")
    selected = upcoming.loc[labels[selected_label]]
    home_team = str(selected["home_team"])
    away_team = str(selected["away_team"])
    event_date = pd.Timestamp(selected["date"])

    expected_home, expected_away = model.expected_goals(home_team, away_team)
    reliability = model.match_reliability(home_team, away_team)
    adjusted_total_mean = (
        reliability * (expected_home + expected_away)
        + (1.0 - reliability) * league_total_prior
    )
    suggested_line = round(adjusted_total_mean - 0.5) + 0.5

    bookmaker_col, line_col, over_col, under_col = st.columns(4)
    with bookmaker_col:
        bookmaker = st.selectbox("Vedonvälittäjä", BOOKMAKERS)
    with line_col:
        total_line = st.number_input(
            "Maaliraja", min_value=0.5, value=float(suggested_line), step=0.5
        )
    with over_col:
        over_odds = st.number_input(
            "Over-kerroin", min_value=1.01, value=1.90, step=0.01
        )
    with under_col:
        under_odds = st.number_input(
            "Under-kerroin", min_value=1.01, value=1.90, step=0.01
        )

    raw_single = prediction_row(
        model,
        event_date,
        home_team,
        away_team,
        total_line,
        over_odds,
        under_odds,
    )
    adjusted_over, adjusted_under = market_anchored_total_probabilities(
        raw_single.over_probability,
        raw_single.push_probability,
        over_odds,
        under_odds,
        reliability,
    )
    adjusted_over_ev = expected_value_with_push(
        adjusted_over, raw_single.push_probability, over_odds
    )
    adjusted_under_ev = expected_value_with_push(
        adjusted_under, raw_single.push_probability, under_odds
    )
    adjusted_over_fair = fair_odds_with_push(adjusted_over, raw_single.push_probability)
    adjusted_under_fair = fair_odds_with_push(adjusted_under, raw_single.push_probability)
    best_side = "Over" if adjusted_over_ev >= adjusted_under_ev else "Under"
    best_ev = float(max(adjusted_over_ev, adjusted_under_ev))

    st.divider()
    metrics = st.columns(5)
    metrics[0].metric("Säädetty maaliodotus", f"{adjusted_total_mean:.2f}")
    metrics[1].metric(
        "Over", f"{adjusted_over:.1%}", f"{adjusted_over_ev:+.1%}"
    )
    metrics[2].metric(
        "Under", f"{adjusted_under:.1%}", f"{adjusted_under_ev:+.1%}"
    )
    metrics[3].metric("Reilu Over", f"{adjusted_over_fair:.2f}")
    metrics[4].metric("Reilu Under", f"{adjusted_under_fair:.2f}")

    if reliability < 0.25:
        st.warning(
            "Tämän ottelun dataluotettavuus on matala. Arvio on ankkuroitu vahvasti "
            "markkinan marginaalittomaan todennäköisyyteen, jotta pieni ottelumäärä "
            "ei synnytä epärealistisia value-signaaleja."
        )

    if best_ev >= ev_limit:
        st.success(
            f"Mahdollinen value: {best_side} {total_line:g} ({bookmaker}). "
            f"Mallin EV {best_ev:+.1%}."
        )
    else:
        st.info(f"Ei value-rajan ylittävää vetoa. Paras EV on {best_ev:+.1%}.")

    with st.expander("Näytä raakamallin arvio"):
        st.write(
            f"Raakamallin maaliodotus on {raw_single.expected_total_goals:.2f} "
            f"({home_team} {expected_home:.2f} – {expected_away:.2f} {away_team}). "
            f"Raakamallin Over-arvio on {raw_single.over_probability:.1%}. "
            "Näitä lukuja ei käytetä sellaisenaan EV-päätökseen, jos joukkueesta "
            "on vähän tuoretta dataa."
        )

with compare_tab:
    st.subheader("Vertaa neljää vedonvälittäjää samalla kertaa")
    st.write(
        "Valitse ottelu ja liitä kertoimet taulukkoon. Voit kopioida useita "
        "Excel-/CSV-soluja ja liittää ne taulukkoon yhdellä Ctrl+V-painalluksella."
    )
    compare_label = st.selectbox("Ottelu", list(labels), key="compare_fixture")
    compare_fixture = upcoming.loc[labels[compare_label]]
    compare_home = str(compare_fixture["home_team"])
    compare_away = str(compare_fixture["away_team"])
    compare_date = pd.Timestamp(compare_fixture["date"])
    compare_home_goals, compare_away_goals = model.expected_goals(compare_home, compare_away)
    compare_reliability = model.match_reliability(compare_home, compare_away)
    compare_total_mean = (
        compare_reliability * (compare_home_goals + compare_away_goals)
        + (1.0 - compare_reliability) * league_total_prior
    )
    compare_line = round(compare_total_mean - 0.5) + 0.5

    odds_grid = pd.DataFrame(
        {
            "Vedonvälittäjä": BOOKMAKERS,
            "Maaliraja": [compare_line] * len(BOOKMAKERS),
            "Over": [None] * len(BOOKMAKERS),
            "Under": [None] * len(BOOKMAKERS),
        }
    )
    edited_odds = st.data_editor(
        odds_grid,
        width="stretch",
        hide_index=True,
        disabled=["Vedonvälittäjä"],
        column_config={
            "Maaliraja": st.column_config.NumberColumn(min_value=0.5, step=0.5),
            "Over": st.column_config.NumberColumn(min_value=1.01, step=0.01),
            "Under": st.column_config.NumberColumn(min_value=1.01, step=0.01),
        },
        key=f"odds_{compare_home}_{compare_away}",
    )

    if st.button("Laske ja järjestä parhaat", type="primary", width="stretch"):
        rows: list[dict[str, object]] = []
        for quote in edited_odds.itertuples(index=False):
            line = pd.to_numeric(quote.Maaliraja, errors="coerce")
            over = pd.to_numeric(quote.Over, errors="coerce")
            under = pd.to_numeric(quote.Under, errors="coerce")
            if pd.isna(line) or pd.isna(over) or pd.isna(under):
                continue
            if float(over) <= 1.0 or float(under) <= 1.0:
                continue
            prediction = prediction_row(
                model,
                compare_date,
                compare_home,
                compare_away,
                float(line),
                float(over),
                float(under),
            )
            adjusted_over, adjusted_under = market_anchored_total_probabilities(
                prediction.over_probability,
                prediction.push_probability,
                float(over),
                float(under),
                compare_reliability,
            )
            adjusted_over_ev = expected_value_with_push(
                adjusted_over, prediction.push_probability, float(over)
            )
            adjusted_under_ev = expected_value_with_push(
                adjusted_under, prediction.push_probability, float(under)
            )
            rows.extend(
                [
                    {
                        "Vedonvälittäjä": quote.Vedonvälittäjä,
                        "Puoli": "Over",
                        "Raja": line,
                        "Kerroin": over,
                        "Reilu kerroin": fair_odds_with_push(
                            adjusted_over, prediction.push_probability
                        ),
                        "Todennäköisyys": adjusted_over,
                        "EV": adjusted_over_ev,
                        "Dataluotettavuus": compare_reliability,
                    },
                    {
                        "Vedonvälittäjä": quote.Vedonvälittäjä,
                        "Puoli": "Under",
                        "Raja": line,
                        "Kerroin": under,
                        "Reilu kerroin": fair_odds_with_push(
                            adjusted_under, prediction.push_probability
                        ),
                        "Todennäköisyys": adjusted_under,
                        "EV": adjusted_under_ev,
                        "Dataluotettavuus": compare_reliability,
                    },
                ]
            )
        if not rows:
            st.warning("Lisää vähintään yhden vedonvälittäjän Over- ja Under-kertoimet.")
        else:
            comparison = pd.DataFrame(rows).sort_values("EV", ascending=False)
            comparison.insert(0, "Value", comparison["EV"] >= ev_limit)
            st.dataframe(
                comparison.style.format(
                    {
                        "Raja": "{:.1f}",
                        "Kerroin": "{:.2f}",
                        "Reilu kerroin": "{:.2f}",
                        "Todennäköisyys": "{:.1%}",
                        "EV": "{:+.1%}",
                        "Dataluotettavuus": "{:.0%}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

with bets_tab:
    st.subheader("Vedon kirjaus")
    with st.form("bet_form"):
        bet_bookmaker = st.selectbox("Vedonvälittäjä", BOOKMAKERS, key="bet_book")
        bet_fixture = st.selectbox("Ottelu", list(labels), key="bet_fixture")
        bet_selected = upcoming.loc[labels[bet_fixture]]
        bet_columns = st.columns(4)
        with bet_columns[0]:
            bet_line = st.number_input("Raja", min_value=0.5, value=10.5, step=0.5)
        with bet_columns[1]:
            bet_side = st.selectbox("Puoli", ["over", "under"])
        with bet_columns[2]:
            bet_odds = st.number_input("Kerroin", min_value=1.01, value=1.90, step=0.01)
        with bet_columns[3]:
            bet_stake = st.number_input("Panos", min_value=0.01, value=10.0, step=1.0)
        submitted = st.form_submit_button("Kirjaa veto", type="primary")
    if submitted:
        try:
            with OddsDatabase(ODDS_DB_PATH) as database:
                bet_id = database.record_bet(
                    bookmaker=bet_bookmaker,
                    event_start=pd.Timestamp(bet_selected["date"]).isoformat(),
                    home_team=str(bet_selected["home_team"]),
                    away_team=str(bet_selected["away_team"]),
                    total_line=bet_line,
                    side=bet_side,
                    decimal_odds=bet_odds,
                    stake=bet_stake,
                )
            st.success(f"Veto {bet_id} kirjattiin.")
        except (OSError, ValueError) as error:
            st.error(str(error))

    if st.button("Näytä CLV-raportti"):
        with OddsDatabase(ODDS_DB_PATH) as database:
            clv_report = database.clv_report()
        if clv_report.empty:
            st.info("Ei vielä kirjattuja vetoja tai päätöskertoimia.")
        else:
            st.dataframe(clv_report, width="stretch", hide_index=True)

with data_tab:
    st.subheader("Päivitä F-liigan ottelutiedot")
    st.write(
        f"Käytössä {len(games)} tulosta ja {len(upcoming)} tulevaa ottelua. "
        "Päivitys hakee ottelut F-liigan julkisesta rajapinnasta."
    )
    if st.button("Päivitä ottelut nyt", type="primary"):
        with st.spinner("Haetaan F-liigan otteluita..."):
            try:
                collected = FliigaCollector().collect()
                collected.completed.to_csv(GAMES_PATH, index=False)
                collected.fixtures.to_csv(FIXTURES_PATH, index=False)
                st.success(
                    f"Päivitetty: {len(collected.completed)} tulosta ja "
                    f"{len(collected.fixtures)} tulevaa ottelua. Käynnistä sivu uudelleen."
                )
            except (OSError, RuntimeError, ValueError) as error:
                st.error(f"Päivitys epäonnistui: {error}")

    st.divider()
    st.caption(
        "Täysin automaattinen vedonvälittäjäkohtaisten kertoimien haku vaatii "
        "lisensoidun odds-API:n. Ilmainen versio ei kierrä kirjautumisia tai bottisuojauksia."
    )
