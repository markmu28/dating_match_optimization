@echo off
chcp 65001 > nul
title 相亲活动分组优化工具

echo ================================================
echo     相亲活动分组优化工具
echo     Dating Match Optimization System
echo ================================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python环境
    echo 请安装Python后重新运行
    pause
    exit /b 1
)

:: 检查依赖
echo 🔍 检查依赖库...
python -c "import tkinter, pandas, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  首次运行检测到缺少必要依赖库
    echo 📦 正在自动安装依赖库...
    echo    这可能需要几分钟时间，请耐心等待...
    echo.
    
    REM 尝试使用pip安装
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ⚠️  pip安装失败，尝试使用python -m pip...
        python -m pip install -r requirements.txt
        if errorlevel 1 (
            echo.
            echo ❌ 自动安装失败！
            echo.
            echo 📋 手动安装方法：
            echo    1. 打开命令提示符（cmd）
            echo    2. 进入此目录: cd /d "%~dp0"
            echo    3. 运行: pip install -r requirements.txt
            echo    4. 或者: pip install pandas openpyxl
            echo.
            pause
            exit /b 1
        )
    )
    
    REM 再次验证安装
    echo.
    echo ✅ 依赖库安装完成，正在验证...
    python -c "import tkinter, pandas, openpyxl" >nul 2>&1
    if errorlevel 1 (
        echo ❌ 验证失败，某些依赖库仍然缺失
        echo 请尝试手动安装: pip install pandas openpyxl
        pause
        exit /b 1
    )
    echo ✅ 所有依赖库验证通过！
    echo.
)

:: 确保outputs目录存在
if not exist "outputs" mkdir outputs

echo ✅ 环境检查完成
echo 🚀 启动图形界面...
echo.

:: 启动GUI程序
python interactive_gui.py

:: 等待用户按键后退出
echo.
echo 程序已退出
pause