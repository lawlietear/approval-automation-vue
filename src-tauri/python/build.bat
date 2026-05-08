@echo off
cd /d %~dp0
python -m PyInstaller --clean runner.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)
copy /Y config.json "dist\ApprovalRunner\config.json"
echo [OK] Python runner built. Output: python/dist/ApprovalRunner/
pause
