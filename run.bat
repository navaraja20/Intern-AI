@echo off
setlocal enabledelayedexpansion
title InternAI  –  Launcher
color 0B

echo.
echo =====================================================
echo   InternAI  –  Starting services
echo =====================================================
echo.

:: ── Load .env ────────────────────────────────────────────────────────────────
if not exist ".env" (
    echo [ERROR] .env not found. Run setup.bat first.
    pause & exit /b 1
)

:: ── Ensure PostgreSQL is running (via Docker) ────────────────────────────────
where docker >nul 2>&1
if not errorlevel 1 (
    docker compose up postgres -d 2>nul || docker-compose up postgres -d
    echo [OK] PostgreSQL container running
)

:: ── Ensure Ollama is running ─────────────────────────────────────────────────
where ollama >nul 2>&1
if not errorlevel 1 (
    tasklist /fi "imagename eq ollama.exe" /fo csv 2>nul | find "ollama.exe" >nul
    if errorlevel 1 (
        echo Starting Ollama server...
        start "Ollama" /min ollama serve
        timeout /t 3 /nobreak >nul
    ) else (
        echo [OK] Ollama already running
    )
)

:: ── Start FastAPI Backend ────────────────────────────────────────────────────
echo.
echo Starting FastAPI backend on http://localhost:8000 ...
if exist "backend\.venv\Scripts\uvicorn.exe" (
    set UV=backend\.venv\Scripts\uvicorn.exe
) else (
    where uvicorn >nul 2>&1
    if not errorlevel 1 (set UV=uvicorn) else (
        echo [ERROR] uvicorn not found. Run setup.bat first.
        pause & exit /b 1
    )
)
start "InternAI Backend" cmd /k "cd backend && ..\%UV% main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 4 /nobreak >nul

:: ── Start Streamlit Frontend ─────────────────────────────────────────────────
echo Starting Streamlit frontend on http://localhost:8501 ...
if exist "frontend\.venv\Scripts\streamlit.exe" (
    set ST=frontend\.venv\Scripts\streamlit.exe
) else (
    where streamlit >nul 2>&1
    if not errorlevel 1 (set ST=streamlit) else (
        echo [ERROR] streamlit not found. Run setup.bat first.
        pause & exit /b 1
    )
)
start "InternAI Frontend" cmd /k "cd frontend && ..\%ST% run app.py --server.port 8501 --server.address localhost"
timeout /t 3 /nobreak >nul

:: ── Open browser ─────────────────────────────────────────────────────────────
echo.
echo =====================================================
echo   InternAI is running!
echo   Frontend:  http://localhost:8501
echo   API docs:  http://localhost:8000/docs
echo =====================================================
echo.
start "" "http://localhost:8501"

pause
