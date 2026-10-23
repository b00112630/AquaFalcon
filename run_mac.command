#!/bin/bash
# Double-click to start the chatbot (first run installs the libraries)
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
streamlit run app.py
