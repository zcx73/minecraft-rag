@echo off
rem 启动问答：不带参数进入连续对话模式，带参数则直接问一句
rem   scripts\run.bat                          -> 连续对话
rem   scripts\run.bat "钻石在哪挖"             -> 问一句
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo 还没准备好环境，请先运行 scripts\setup.bat
    exit /b 1
)

if "%~1"=="" (
    ".venv\Scripts\python.exe" -m src.cli chat
) else (
    ".venv\Scripts\python.exe" -m src.cli ask "%~1"
)
endlocal
