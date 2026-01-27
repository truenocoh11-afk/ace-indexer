@echo off
echo [ACE] Setting up local environment...
if not exist "venv" (
    echo [ACE] Creating virtual environment...
    python -m venv venv
) else (
    echo [ACE] Virtual environment already exists.
)

echo [ACE] Installing dependencies...
call venv\Scripts\activate
pip install -r requirements.txt

echo.
echo [ACE] Setup complete! You can now run start.bat
pause
