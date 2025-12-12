@echo off
REM Quick test script for Windows
REM Run this to test stage implementation

echo.
echo ============================================
echo   Stage Implementation Testing
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Please create .env file from .env.example
    pause
    exit /b 1
)

REM Check if server is running
echo Checking if server is running on port 8009...
netstat -an | find "8009" | find "LISTENING" >nul
if errorlevel 1 (
    echo.
    echo WARNING: Server doesn't appear to be running!
    echo Please start the server in another terminal:
    echo    uv run python scripts/run_api.py
    echo.
    pause
)

echo.
echo Running tests...
echo.
python test_stages.py

pause
