#!/usr/bin/env sh
set -e
if [ -x ".venv/bin/python" ]; then
  .venv/bin/python -m streamlit run app.py
else
  python3 -m streamlit run app.py
fi
