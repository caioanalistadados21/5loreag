@echo off
setlocal

if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Instalacao concluida.
echo Copie secrets.example.toml para secrets.toml na raiz ^(ou use .streamlit\secrets.toml^) e preencha as credenciais Google.
echo Depois execute run.bat.
pause
