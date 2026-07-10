@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

echo === 太初一键启动 ===

call :load_env MONGODB_HOME
call :load_env MONGODB_DATA_DIR
call :load_env MONGODB_LOG_DIR
call :load_env MONGODB_URI
call :load_env MONGODB_DATABASE
call :load_env PROJECT_ASSETS_DIR

if not defined MONGODB_HOME (
    echo [错误] 未配置 MONGODB_HOME，请检查当前用户环境变量或项目 .env。
    goto :startup_error
)
if not defined MONGODB_DATA_DIR (
    echo [错误] 未配置 MONGODB_DATA_DIR，请检查当前用户环境变量或项目 .env。
    goto :startup_error
)
if not defined MONGODB_LOG_DIR (
    echo [错误] 未配置 MONGODB_LOG_DIR，请检查当前用户环境变量或项目 .env。
    goto :startup_error
)
if not exist "%MONGODB_HOME%\bin\mongod.exe" (
    echo [错误] 找不到 MongoDB 服务程序：%MONGODB_HOME%\bin\mongod.exe
    goto :startup_error
)

if not exist "%MONGODB_DATA_DIR%" mkdir "%MONGODB_DATA_DIR%"
if not exist "%MONGODB_LOG_DIR%" mkdir "%MONGODB_LOG_DIR%"

echo [1/3] 检查 MongoDB 服务...
set "MONGO_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":27017 .*LISTENING"') do if not defined MONGO_PID set "MONGO_PID=%%a"
if defined MONGO_PID (
    tasklist /FI "PID eq !MONGO_PID!" /FO CSV /NH | findstr /I "mongod.exe" >nul
    if errorlevel 1 (
        echo [错误] 端口 27017 已被非 MongoDB 进程占用，进程号：!MONGO_PID!。
        goto :startup_error
    )
    echo   已复用正在运行的 MongoDB，进程号：!MONGO_PID!。
) else (
    start "太初 MongoDB" /min "%MONGODB_HOME%\bin\mongod.exe" --bind_ip 127.0.0.1 --port 27017 --dbpath "%MONGODB_DATA_DIR%" --logpath "%MONGODB_LOG_DIR%\mongod.log" --logappend
    timeout /t 3 /nobreak >nul
    netstat -ano | findstr /R /C:":27017 .*LISTENING" >nul
    if errorlevel 1 (
        echo [错误] MongoDB 启动失败，请检查日志：%MONGODB_LOG_DIR%\mongod.log
        goto :startup_error
    )
    echo   MongoDB 已启动，数据目录：%MONGODB_DATA_DIR%
)

echo [2/3] 清理后端 8000 和前端 3000 端口...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 "') do taskkill /F /PID %%a 2>nul
echo   端口清理完成。

echo [3/3] 启动后端和前端...
start "太初后端" cmd /c "cd /d %~dp0 && uv run taichu"
start "太初前端" cmd /c "cd /d %~dp0web && npm run dev"

timeout /t 5 /nobreak >nul
echo.
echo === 太初已启动 ===
echo   前端：http://localhost:3000
echo   后端：http://127.0.0.1:8000
echo   MongoDB：%MONGODB_URI%
echo   关闭对应命令窗口即可停止服务。
echo.
pause
exit /b 0

:load_env
if defined %~1 exit /b 0
if not exist "%~dp0.env" exit /b 0
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
    if /I "%%A"=="%~1" set "%~1=%%B"
)
exit /b 0

:startup_error
echo.
echo 太初启动已中止。
pause
exit /b 1
