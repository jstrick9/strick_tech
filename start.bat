@echo off
REM ═══════════════════════════════════════════════════════════════
REM  Agentic OS — Startup Script (Windows)
REM  Run: start.bat
REM ═══════════════════════════════════════════════════════════════

echo.
echo   🧠 Agentic OS v6.0 — Mission Control
echo   ══════════════════════════════════════
echo.

REM ── Check Python ─────────────────────────────────────────────
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   ❌ Python not found.
    echo      Install: https://python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo   ✅ Python: %PYVER%

REM ── Check .env ───────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        echo.
        echo   ⚠️  No .env file found.
        echo      Copying .env.example to .env
        copy .env.example .env
        echo      Edit .env and add your OPENROUTER_API_KEY
        echo      Get a free key: https://openrouter.ai/keys
        echo.
    )
)

REM ── Install dependencies ────────────────────────────────────
echo.
echo   📦 Checking dependencies...
python -c "import fastapi" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   Installing requirements...
    python -m pip install -r requirements.txt -q
)

REM ── Run ──────────────────────────────────────────────────────
echo.
echo   🚀 Starting Agentic OS...
echo   🌐 http://localhost:8787
echo.

python run.py
pause
