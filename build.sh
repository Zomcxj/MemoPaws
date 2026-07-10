#!/bin/bash

# ==============================================================================
#  MemoPaws 构建脚本
#  离线截图 OCR 翻译与编辑工具
#  支持: Linux / Windows (MSYS2 / Git Bash / Cygwin) / macOS
#  用法: ./build.sh [options]
#  选项:
#    --clean       : 强制清理缓存，从头构建（默认）
#    --no-clean    : 使用缓存，加快重复构建速度（推荐日常开发）
#    --portable    : 打包为便携版单文件
#
#  快捷方式:
#    ./build.sh           # 完整构建（发布版本）
#    ./build.sh fast      # 快速构建（日常开发）= --no-clean
#    ./build.sh portable  # 便携版单文件
# ==============================================================================

# 记录项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# 解析命令行参数
CLEAN_BUILD=true
PORTABLE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        --no-clean)
            CLEAN_BUILD=false
            shift
            ;;
        --portable)
            PORTABLE=true
            shift
            ;;
        fast)
            CLEAN_BUILD=false
            shift
            ;;
        portable)
            PORTABLE=true
            shift
            ;;
        *)
            echo "未知参数: $1"
            echo "用法: $0 [--clean|--no-clean] | fast | portable"
            exit 1
            ;;
    esac
done

set -e

# ==================== 颜色输出定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { printf "%b[INFO]%b  %s %s\n" "$BLUE" "$NC" "$(date '+%H:%M:%S')" "$*"; }
log_ok()    { printf "%b[OK]%b    %s %s\n" "$GREEN" "$NC" "$(date '+%H:%M:%S')" "$*"; }
log_warn()  { printf "%b[WARN]%b  %s %s\n" "$YELLOW" "$NC" "$(date '+%H:%M:%S')" "$*"; }
log_error() { printf "%b[ERROR]%b %s %s\n" "$RED" "$NC" "$(date '+%H:%M:%S')" "$*"; }

# ==================== 检测操作系统 ====================
log_info "检测操作系统..."
OS="$(uname -s)"
case "$OS" in
    Linux*)     PLATFORM="linux" ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT) PLATFORM="windows" ;;
    Darwin*)    PLATFORM="macos" ;;
    *)
        log_error "不支持的操作系统: $OS"
        exit 1
        ;;
esac
log_ok "当前平台: $PLATFORM (uname: $OS)"

# ==================== 平台相关配置 ====================
if [ "$PLATFORM" = "windows" ]; then
    LLM_ENV_ROOT="/d/software/miniforge3/envs/llm"
    LLM_PYTHON="$LLM_ENV_ROOT/python.exe"
    if [ -x "$LLM_PYTHON" ]; then
        PYTHON_BIN="$LLM_PYTHON"
    else
        PYTHON_BIN="python"
    fi
    PYINSTALLER_CMD="\"$PYTHON_BIN\" -m PyInstaller"
    ADD_DATA_SEP=";"
    EXTRA_ARGS=""
    OPENSSL_SSL_DLL="$(cygpath -w "$LLM_ENV_ROOT/Library/bin/libssl-3-x64.dll" 2>/dev/null || echo "$LLM_ENV_ROOT/Library/bin/libssl-3-x64.dll")"
    OPENSSL_CRYPTO_DLL="$(cygpath -w "$LLM_ENV_ROOT/Library/bin/libcrypto-3-x64.dll" 2>/dev/null || echo "$LLM_ENV_ROOT/Library/bin/libcrypto-3-x64.dll")"
    OPENSSL_BINARY_ARGS="--add-binary \"${OPENSSL_SSL_DLL}${ADD_DATA_SEP}.\" --add-binary \"${OPENSSL_CRYPTO_DLL}${ADD_DATA_SEP}.\""
    PROJECT_ROOT="$(cygpath -w "$PROJECT_ROOT" 2>/dev/null || echo "$PROJECT_ROOT")"
    OUTPUT_FILE="${PROJECT_ROOT}/dist/MemoPaws_Portable.exe"
else
    PYINSTALLER_CMD="pyinstaller"
    ADD_DATA_SEP=":"
    EXTRA_ARGS=""
    OPENSSL_BINARY_ARGS=""
    OUTPUT_FILE="${PROJECT_ROOT}/dist/MemoPaws"
fi

log_info "PyInstaller 命令: $PYINSTALLER_CMD"
log_info "资源路径分隔符:   '$ADD_DATA_SEP'"

# ==================== 前置检查 ====================
log_info "执行前置检查..."

# 检查 PyInstaller
if [ "$PLATFORM" = "windows" ]; then
    if ! command -v "$PYTHON_BIN" &> /dev/null; then
        log_error "未找到 python，请确保 Python 已安装并加入 PATH"
        exit 1
    fi
    log_info "Python 解释器: $($PYTHON_BIN -c 'import sys; print(sys.executable)')"
    if ! "$PYTHON_BIN" -m PyInstaller --version &> /dev/null; then
        log_error "未找到 PyInstaller，请执行: pip install pyinstaller"
        exit 1
    fi
else
    if ! command -v pyinstaller &> /dev/null; then
        log_error "未找到 pyinstaller，请执行: pip install pyinstaller"
        exit 1
    fi
fi
log_ok "PyInstaller 可用"

# 检查主脚本
MAIN_SCRIPT="main.py"
if [ ! -f "$MAIN_SCRIPT" ]; then
    log_error "主脚本 '$MAIN_SCRIPT' 不存在于 $(pwd)"
    exit 1
fi
log_ok "主脚本 '$MAIN_SCRIPT' 存在"

# 检查图标
ICON_FILE="${PROJECT_ROOT}/assets/app.ico"
if [ ! -f "$ICON_FILE" ]; then
    log_warn "图标文件 '$ICON_FILE' 不存在，构建将继续但可能缺少图标"
else
    log_ok "图标文件 '$ICON_FILE' 存在"
fi

# 检查资源目录
ASSETS_DIR="${PROJECT_ROOT}/assets"
ICONS_DIR="${ASSETS_DIR}/icons"
FONTS_DIR="${ASSETS_DIR}/fonts"
RESOURCES_DIR="${PROJECT_ROOT}/memopaws/resources"

if [ -d "$ICONS_DIR" ]; then
    ICON_COUNT=$(find "$ICONS_DIR" -name "*.svg" 2>/dev/null | wc -l)
    log_ok "图标目录: $ICON_COUNT 个 SVG"
else
    log_warn "图标目录不存在: $ICONS_DIR"
fi

if [ -d "$FONTS_DIR" ]; then
    FONT_COUNT=$(find "$FONTS_DIR" -name "*.ttf" 2>/dev/null | wc -l)
    log_ok "字体目录: $FONT_COUNT 个 TTF"
else
    log_warn "字体目录不存在: $FONTS_DIR"
fi

if [ "$PLATFORM" = "windows" ]; then
    for dll in "$OPENSSL_SSL_DLL" "$OPENSSL_CRYPTO_DLL"; do
        if [ ! -f "$dll" ]; then
            log_error "缺少 OpenSSL DLL: $dll"
            exit 1
        fi
    done
    log_ok "OpenSSL DLL 已找到"
fi

# ==================== 打包模式选择 ====================
if [ "$PORTABLE" = true ]; then
    log_info "模式: 便携版单文件"
    MODE_ARGS="-F"
    OUTPUT_NAME="MemoPaws_Portable"
    OUTPUT_FILE="${PROJECT_ROOT}/dist/MemoPaws_Portable.exe"
else
    log_info "模式: 目录打包（推荐）"
    MODE_ARGS="-D"
    OUTPUT_NAME="MemoPaws"
    OUTPUT_FILE="${PROJECT_ROOT}/dist/MemoPaws"
fi

# ==================== 执行打包 ====================
log_info "开始打包 ${PLATFORM} 应用程序..."

# 构建命令
PYINSTALLER_CMD_LINE="$PYINSTALLER_CMD \
    $MODE_ARGS \
    -w \
    -n $OUTPUT_NAME \
    --distpath \"${PROJECT_ROOT}/dist\" \
    --workpath \"${PROJECT_ROOT}/build\" \
    --specpath \"${PROJECT_ROOT}\" \
    --icon=\"${ICON_FILE}\" \
    --add-data \"${ASSETS_DIR}${ADD_DATA_SEP}assets\" \
    --add-data \"${RESOURCES_DIR}${ADD_DATA_SEP}memopaws/resources\" \
    $OPENSSL_BINARY_ARGS \
    --hidden-import=PySide6.QtSvg \
    --hidden-import=PySide6.QtSvgWidgets \
    --hidden-import=rapidocr \
    --hidden-import=onnxruntime \
    --hidden-import=httpx \
    --hidden-import=pynput.keyboard._win32 \
    --hidden-import=pynput.mouse._win32 \
    --hidden-import=pynput._util.win32 \
    --hidden-import=pynput._util.win32_vks \
    --hidden-import=numpy \
    --hidden-import=cv2 \
    --hidden-import=PIL \
    --exclude-module tkinter \
    --exclude-module PyQt5 \
    --exclude-module PyQt6 \
    --exclude-module matplotlib \
    --exclude-module pandas \
    --exclude-module torch \
    --exclude-module torchvision \
    --exclude-module torchaudio \
    --exclude-module tensorflow \
    --exclude-module keras \
    --exclude-module sklearn \
    --exclude-module scipy \
    --exclude-module pytest \
    --noconfirm \
    $EXTRA_ARGS \
    \"$MAIN_SCRIPT\""

log_info "执行命令:"
echo "─────────────────────────────────────────"
echo "$PYINSTALLER_CMD_LINE"
echo "─────────────────────────────────────────"

if [ "$CLEAN_BUILD" = true ]; then
    log_info "清理模式：重新分析所有依赖（适合发布版本）"
    eval "$PYINSTALLER_CMD_LINE --clean"
else
    log_info "快速模式：使用缓存构建（适合日常开发）"
    eval "$PYINSTALLER_CMD_LINE"
fi

BUILD_EXIT_CODE=$?

# ==================== 结果处理 ====================
echo ""
if [ $BUILD_EXIT_CODE -eq 0 ]; then
    if [ -f "$OUTPUT_FILE" ] || [ -d "$OUTPUT_FILE" ]; then
        if [ -f "$OUTPUT_FILE" ]; then
            FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
        else
            FILE_SIZE=$(du -sh "$OUTPUT_FILE" | cut -f1)
        fi
        log_ok "打包成功！"
        log_ok "输出: ${OUTPUT_FILE} (${FILE_SIZE})"
    else
        log_warn "打包命令执行成功，但未找到输出文件"
        log_warn "请检查 ${PROJECT_ROOT}/dist/ 目录"
    fi
    echo ""
    log_info "应用程序特性："
    log_info "  - 无控制台窗口 (-w)"
    if [ "$PORTABLE" = true ]; then
        log_info "  - 单文件便携版 (-F)"
    else
        log_info "  - 目录打包 (-D)"
    fi
    log_info "  - 应用图标: ${ICON_FILE}"
    log_info "  - 包含: icons/ + fonts/ + resources/"
    log_info "  - 内置: PySide6 + RapidOCR + OnnxRuntime + httpx"
    exit 0
else
    log_error "打包失败 (退出码: $BUILD_EXIT_CODE)，请检查上方错误信息"
    exit 1
fi
