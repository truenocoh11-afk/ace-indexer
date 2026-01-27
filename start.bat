@echo off
TITLE ACE SERVER - DO NOT CLOSE [Running on Port 8000]
COLOR 0A

:: Ensure we are in the right directory
cd /d "%~dp0"

cls
echo ========================================================
echo       ANTIGRAVITY CONTEXT ENGINE (ACE) - ONLINE
echo ========================================================
echo.
echo    [WARNING]  DO NOT CLOSE THIS WINDOW
echo    [STATUS]   Listening for Agents on:
echo               - HTTP: http://localhost:8000
echo               - MCP:  http://localhost:8000/sse
echo.
echo ========================================================
echo.

call venv\Scripts\activate

:: Start Uvicorn Server
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
