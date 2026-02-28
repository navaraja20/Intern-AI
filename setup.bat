@echo off
setlocal enabledelayedexpansion
title InternAI  –  Setup
color 0A

echo.
echo =====================================================
echo   InternAI  –  First-time Setup
echo =====================================================
echo.

:: ── Check Python ────────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and re-run.
    pause & exit /b 1
)
for /f "delims=" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] %PYVER%

:: ── Check Ollama ─────────────────────────────────────────────────────────────
where ollama >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama not found. Download from https://ollama.com
) else (
    echo [OK] Ollama found
    echo Pulling llama3.1:8b if not already downloaded...
    ollama pull llama3.1:8b
)

:: ── Copy .env ────────────────────────────────────────────────────────────────
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [OK] Created .env  -- Edit POSTGRES_PASSWORD and SECRET_KEY before production use
) else (
    echo [OK] .env already exists
)

:: ── Create virtual envs ──────────────────────────────────────────────────────
echo.
echo [1/2] Setting up BACKEND virtual environment...
if not exist "backend\.venv" (
    python -m venv backend\.venv
)
call backend\.venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.backend.txt -q
echo [OK] Backend packages installed
call deactivate

echo.
echo [2/2] Setting up FRONTEND virtual environment...
if not exist "frontend\.venv" (
    python -m venv frontend\.venv
)
call frontend\.venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.frontend.txt -q
echo [OK] Frontend packages installed
call deactivate

:: ── Docker check ─────────────────────────────────────────────────────────────
echo.
where docker >nul 2>&1
if errorlevel 1 (
    echo [WARN] Docker not found. Install Docker Desktop to run PostgreSQL.
    echo        Alternatively set POSTGRES_HOST to an existing PostgreSQL server in .env
) else (
    echo [OK] Docker found
    echo Starting PostgreSQL container...
    docker compose up postgres -d 2>nul || docker-compose up postgres -d
    echo Waiting for PostgreSQL to be ready...
    timeout /t 5 /nobreak >nul
)

echo.
echo =====================================================
echo   Setup complete!  Run  run.bat  to start InternAI
echo =====================================================
echo.
pause
