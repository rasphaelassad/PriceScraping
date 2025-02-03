@echo off
echo Starting test suite with FastAPI server...
echo.
echo To debug:
echo 1. Open VS Code Debug view (Ctrl+Shift+D)
echo 2. Select "Server + Tests" from the dropdown
echo 3. Press F5 to start debugging
echo.
echo Or press any key to run without debugging...
pause > nul

python run_tests.py
if errorlevel 1 (
    echo Tests failed!
    pause
    exit /b 1
)
echo All tests completed successfully!
pause 