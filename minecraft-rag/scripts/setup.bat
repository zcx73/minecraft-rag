@echo off
rem ===================================================================
rem  一键准备环境：创建虚拟环境 + 安装依赖
rem  用法：双击，或在命令行运行  scripts\setup.bat
rem ===================================================================
setlocal
cd /d "%~dp0.."

echo [1/4] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   x 没找到 python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
    exit /b 1
)

echo [2/4] 创建虚拟环境 .venv ...
if exist ".venv\Scripts\python.exe" (
    echo   = .venv 已存在，跳过
) else (
    python -m venv .venv
)

echo [3/4] 安装依赖（优先用清华镜像）...
".venv\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo   ! 在线安装失败，尝试用本地 wheels 目录离线安装...
    python scripts\fetch_wheels.py
    ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt
)

echo [4/4] 构建知识库索引...
".venv\Scripts\python.exe" -m src.cli build
".venv\Scripts\python.exe" -m src.cli doctor

echo.
echo 完成！运行  scripts\run.bat 开始提问。
endlocal
