@echo off
echo === Taichu Startup ===

echo [1/2] Cleaning port 8000 and 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 "') do taskkill /F /PID %%a 2>nul
echo   Done

echo [2/2] Starting backend and frontend...
start "Taichu Backend" cmd /c "cd /d %~dp0 && uv run taichu"
start "Taichu Frontend" cmd /c "cd /d %~dp0web && npm run dev"

timeout /t 5 /nobreak >nul
echo.
echo === Taichu Ready ===
echo   Frontend: http://localhost:3000
echo   Backend:  http://127.0.0.1:8000
echo   Close each cmd window to stop services
echo.
pause
