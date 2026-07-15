@echo off
:: Agentic OS v6.0 — Windows Launcher
title Agentic OS v6.0 — Mission Control
cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Create .env from example if missing
if not exist .env (
    if exist .env.example (
        copy .env.example .env
        echo Created .env from .env.example - add your OPENROUTER_API_KEY
    )
)

:: Install dependencies
echo Installing dependencies...
python -m pip install -r requirements.txt -q

:: Run
echo Starting Agentic OS...
python run.py
pause
