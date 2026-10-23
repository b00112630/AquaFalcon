@echo off
REM Double-click to start the chatbot (first run installs the libraries)
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -q -r requirements.txt
streamlit run app.py
pause
