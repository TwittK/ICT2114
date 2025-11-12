@echo off
echo ==========================================
echo LabComply Test Suite Runner
echo ==========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Navigate to the project root directory (one level up from tests)
cd /d "%~dp0.."

REM Install test dependencies
echo Installing test dependencies...
pip install -r tests\requirements-test.txt

REM Run the tests from project root
echo.
echo Running tests...
echo.
python -m unittest discover -s tests -p "test_*.py" -v

echo.
echo ==========================================
echo Test execution completed!
echo ==========================================
pause