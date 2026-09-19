#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 puuttuu. Asenna Python 3.11 tai uudempi ensin."
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "Ensimmäinen käynnistys: luodaan ohjelmalle oma ympäristö..."
    python3 -m venv .venv
fi

echo "Tarkistetaan tarvittavat paketit..."
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -e ".[app]"

echo "Käynnistetään sovellus selaimeen..."
.venv/bin/python -m streamlit run app.py
