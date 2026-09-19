from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from fliiga_model.data import load_fixtures, load_games
from fliiga_model.market import OddsDatabase, build_value_report
from fliiga_model.model import PoissonStrengthModel
from fliiga_model.predict import predict_fixtures

st.set_page_config(page_title="F-liiga Value Model", page_icon="📊", layout="wide")
st.title("F-liiga Value Model")
st.caption("Miesten F-liigan totals- ja 1X2-todennäköisyydet sekä EV-laskenta.")

with st.sidebar:
    st.header("Mallin asetukset")
    half_life = st.slider("Puoliintumisaika (päivää)", 30, 365, 120)
    l2 = st.slider("Regularisointi", 0.0, 10.0, 1.0, 0.1)
    ev_limit = st.slider("Näytettävä minimi-EV", 0.0, 0.25, 0.05, 0.01)

st.subheader("1. Data")
games_file = st.file_uploader("Korvaa historiadata omalla games.csv-tiedostolla", type="csv")
fixtures_file = st.file_uploader("Lataa bulk-ennusteiden fixtures.csv", type="csv")

bundled_games = Path(__file__).parent / "data" / "fliiga_men_history.csv"
bundled_fixtures = Path(__file__).parent / "data" / "fliiga_men_fixtures.csv"
games_source = games_file if games_file is not None else bundled_games

try:
    games = load_games(games_source)
    model = PoissonStrengthModel(half_life_days=half_life, l2=l2).fit(games)
    st.success(
        f"Käytössä {len(games)} miesten F-liigaottelua ja {len(model.teams)} joukkuetta. "
        f"Totals-dispersio: {model.total_dispersion_:.3f}."
    )
except (OSError, RuntimeError, ValueError) as error:
    st.error(str(error))
    st.stop()

st.subheader("2. Yksittäisen totals-kohteen arvio")
current_teams = model.teams
if bundled_fixtures.exists():
    current_fixture_data = load_fixtures(bundled_fixtures)
    fixture_teams = sorted(
        set(current_fixture_data["home_team"]) | set(current_fixture_data["away_team"])
    )
    current_teams = [team for team in fixture_teams if team in model.team_index]
left, right = st.columns(2)
with left:
    home_team = st.selectbox("Kotijoukkue", current_teams, index=0)
with right:
    away_options = [team for team in current_teams if team != home_team]
    away_team = st.selectbox("Vierasjoukkue", away_options, index=0)

expected_home, expected_away = model.expected_goals(home_team, away_team)
suggested_line = round(expected_home + expected_away - 0.5) + 0.5
line_col, over_col, under_col = st.columns(3)
with line_col:
    total_line = st.number_input("Maaliraja", min_value=0.5, value=float(suggested_line), step=0.5)
with over_col:
    over_odds = st.number_input("Over-kerroin", min_value=1.01, value=1.90, step=0.01)
with under_col:
    under_odds = st.number_input("Under-kerroin", min_value=1.01, value=1.90, step=0.01)

single_fixture = pd.DataFrame(
    [
        {
            "date": pd.Timestamp.now(),
            "home_team": home_team,
            "away_team": away_team,
            "total_line": total_line,
            "over_odds": over_odds,
            "under_odds": under_odds,
        }
    ]
)
single = predict_fixtures(model, single_fixture).iloc[0]
metric_columns = st.columns(4)
metric_columns[0].metric("Odotetut maalit", f"{single.expected_total_goals:.2f}")
metric_columns[1].metric("Over", f"{100 * single.over_probability:.1f} %", f"EV {100 * single.over_ev:.1f} %")
metric_columns[2].metric("Under", f"{100 * single.under_probability:.1f} %", f"EV {100 * single.under_ev:.1f} %")
best_side = "Over" if single.over_ev >= single.under_ev else "Under"
best_ev = max(single.over_ev, single.under_ev)
metric_columns[3].metric("Paras puoli", best_side, f"EV {100 * best_ev:.1f} %")

st.caption(
    f"Mallin maaliennuste: {home_team} {expected_home:.2f} – {expected_away:.2f} {away_team}. "
    "Pelaa vain, jos ero kestää kokoonpano- ja maalivahtitarkistuksen."
)

if fixtures_file:
    try:
        fixtures = load_fixtures(fixtures_file)
        predictions = predict_fixtures(model, fixtures)
        st.subheader("3. Bulk-ennusteet")
        ev_columns = [column for column in predictions if column.endswith("_ev")]
        if ev_columns:
            predictions["best_ev"] = predictions[ev_columns].max(axis=1)
            filtered = predictions[predictions["best_ev"] >= ev_limit]
            st.subheader("Mallin tunnistamat ehdokkaat")
            st.dataframe(filtered, use_container_width=True, hide_index=True)
        else:
            st.info("Lisää fixtures.csv-tiedostoon home_odds, draw_odds ja away_odds EV-laskentaa varten.")
            st.dataframe(predictions, use_container_width=True, hide_index=True)

        st.download_button(
            "Lataa kaikki ennusteet CSV:nä",
            predictions.to_csv(index=False).encode("utf-8"),
            "predictions.csv",
            "text/csv",
        )
    except (OSError, RuntimeError, ValueError) as error:
        st.error(str(error))
else:
    st.info("Bulk-ennusteita varten lataa fixtures.csv. Yksittäinen totals-laskuri toimii yllä ilman tiedostoa.")

st.divider()
st.subheader("4. Kerroinhistoria ja päivän value-lista")
odds_database = Path(__file__).parent / "data" / "odds.db"
odds_upload = st.file_uploader(
    "Tuo vedonvälittäjien totals-kertoimet", type="csv", key="odds_upload"
)
if odds_upload is not None and st.button("Tallenna kertoimet tietokantaan"):
    try:
        with OddsDatabase(odds_database) as database:
            imported = database.import_csv(odds_upload)
        st.success(f"Tallennettiin {imported} uutta kerroinhavaintoa.")
    except (OSError, ValueError) as error:
        st.error(str(error))

if st.button("Laske päivän value-lista"):
    try:
        with OddsDatabase(odds_database) as database:
            value_report = build_value_report(
                database, bundled_games, bundled_fixtures, min_ev=ev_limit,
                half_life=half_life, l2=l2,
            )
        if value_report.empty:
            st.info("Nykyisistä kerroinhavainnoista ei löytynyt rajan ylittävää kohdetta.")
        else:
            st.dataframe(value_report, use_container_width=True, hide_index=True)
            st.download_button(
                "Lataa value-lista CSV:nä", value_report.to_csv(index=False).encode("utf-8"),
                "daily_value.csv", "text/csv",
            )
    except (OSError, RuntimeError, ValueError) as error:
        st.error(str(error))

st.subheader("5. Vedon kirjaus ja CLV")
with st.form("bet_form"):
    bet_bookmaker = st.text_input("Vedonvälittäjä")
    bet_home = st.text_input("Kotijoukkue")
    bet_away = st.text_input("Vierasjoukkue")
    bet_start = st.text_input("Alkamisaika", placeholder="2026-09-20T17:00:00+03:00")
    bet_line, bet_odds, bet_stake = st.columns(3)
    with bet_line:
        recorded_line = st.number_input("Totals-raja", min_value=0.5, value=10.5, step=0.5)
    with bet_odds:
        recorded_odds = st.number_input("Saatu kerroin", min_value=1.01, value=1.90, step=0.01)
    with bet_stake:
        recorded_stake = st.number_input("Panos", min_value=0.01, value=10.0, step=1.0)
    recorded_side = st.selectbox("Puoli", ["over", "under"])
    bet_submitted = st.form_submit_button("Kirjaa veto")
if bet_submitted:
    try:
        with OddsDatabase(odds_database) as database:
            bet_id = database.record_bet(
                bookmaker=bet_bookmaker, event_start=bet_start, home_team=bet_home,
                away_team=bet_away, total_line=recorded_line, side=recorded_side,
                decimal_odds=recorded_odds, stake=recorded_stake,
            )
        st.success(f"Veto {bet_id} kirjattiin.")
    except (OSError, ValueError) as error:
        st.error(str(error))

if st.button("Näytä CLV-raportti"):
    with OddsDatabase(odds_database) as database:
        clv_report = database.clv_report()
    if clv_report.empty:
        st.info("Ei vielä kirjattuja vetoja tai päätöskertoimia.")
    else:
        st.dataframe(clv_report, use_container_width=True, hide_index=True)
        st.download_button(
            "Lataa CLV-raportti CSV:nä", clv_report.to_csv(index=False).encode("utf-8"),
            "clv_report.csv", "text/csv",
        )
