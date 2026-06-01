@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ==========================================
echo CPK Heatmap 平台
echo ==========================================
echo.
echo 正在检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo 未检测到 Python。
    echo 请先安装 Python 3.11 或更高版本，并勾选 Add python.exe to PATH。
    echo 下载地址：https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo.
echo 正在安装/更新运行依赖，首次运行可能需要几分钟...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 依赖安装失败，请检查网络连接后重试。
    echo.
    pause
    exit /b 1
)

echo.
echo 正在启动平台...
echo 浏览器打开后即可使用。如果没有自动打开，请访问 http://localhost:8501
echo 关闭本窗口即可停止平台。
echo.
python -m streamlit run app.py

pause
