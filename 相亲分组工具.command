#!/bin/bash

# 相亲活动分组优化工具 Streamlit 启动脚本
# 双击此文件即可运行 GUI

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "    相亲活动分组优化工具 (Streamlit GUI)"
echo "    Dating Match Optimization System"
echo "================================================"
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到Python3环境"
    echo "请安装Python3后重新运行"
    read -p "按Enter键退出..."
    exit 1
fi

# 检查依赖
echo "🔍 检查依赖库..."
python3 -c "import streamlit, pandas, openpyxl" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  首次运行检测到缺少必要依赖库"
    echo "📦 正在自动安装依赖库..."
    echo "   这可能需要几分钟时间，请耐心等待..."
    echo ""
    
    # 尝试使用pip3安装
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "⚠️  pip3安装失败，尝试使用pip..."
        pip install -r requirements.txt
        if [ $? -ne 0 ]; then
            echo ""
            echo "❌ 自动安装失败！"
            echo ""
            echo "📋 手动安装方法："
            echo "   1. 打开终端/命令行"
            echo "   2. 进入此目录: cd \"$SCRIPT_DIR\""
            echo "   3. 运行: pip3 install -r requirements.txt"
            echo "   4. 或者: pip install streamlit pandas openpyxl"
            echo ""
            read -p "按Enter键退出..."
            exit 1
        fi
    fi
    
    # 再次验证安装
    echo ""
    echo "✅ 依赖库安装完成，正在验证..."
    python3 -c "import streamlit, pandas, openpyxl" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "❌ 验证失败，某些依赖库仍然缺失"
        echo "请尝试手动安装: pip3 install streamlit pandas openpyxl"
        read -p "按Enter键退出..."
        exit 1
    fi
    echo "✅ 所有依赖库验证通过！"
    echo ""
fi

# 确保outputs目录存在
mkdir -p outputs

echo "✅ 环境检查完成"
echo "🚀 启动 Streamlit 图形界面..."
echo ""
echo "如果浏览器未自动打开，请访问: http://localhost:8501"
echo ""

# 启动 Streamlit GUI
python3 -m streamlit run streamlit_app.py --server.headless false --browser.gatherUsageStats false

# 等待用户按键后退出
echo ""
echo "程序已退出"
read -p "按Enter键关闭窗口..."
