@echo off
title Deep Research Agent
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

:menu
cls
echo ==============================================
echo    Deep Research Agent
echo    Multi-agent deep research assistant
echo ==============================================
echo.
echo    1. Launch Web UI (Streamlit)
echo    2. Research via CLI (type a question)
echo    3. Run unit tests
echo    4. Run evals (3 cases)
echo    5. Exit
echo.
echo ----------------------------------------------
set "choice="
set /p choice=Choose [1-5]: 
if "%choice%"=="1" goto web
if "%choice%"=="2" goto cli
if "%choice%"=="3" goto test
if "%choice%"=="4" goto eval
if "%choice%"=="5" goto end
goto menu

:web
cls
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
echo Starting Web UI ... opening http://localhost:8501
echo Close this window to stop the server.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8501
pause
goto menu

:cli
cls
set "question="
set /p question=Enter your research question: 
if "%question%"=="" goto cli
echo Researching, please wait (local model ~1-3 min) ...
".venv\Scripts\python.exe" -m research_agent.cli "%question%"
pause
goto menu

:test
cls
".venv\Scripts\python.exe" -m pytest -q
pause
goto menu

:eval
cls
".venv\Scripts\python.exe" evals\run_evals.py --limit 3 --max-queries 2
pause
goto menu

:end
exit /b 0