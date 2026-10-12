@echo off
title Deep Research Agent - Web UI
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [first-run] creating venv and installing dependencies...
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        "%USERPROFILE%\.local\bin\uv.exe" sync --extra dev --extra web
    ) else (
        echo uv not found. Install from https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
)
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
echo Starting Web UI ... opening http://localhost:8501
echo Close this window to stop the server.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8501
pause