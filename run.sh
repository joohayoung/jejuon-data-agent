#!/bin/sh
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt; }
.venv/bin/python -m streamlit run app.py --server.port 8501
