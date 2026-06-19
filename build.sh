#!/usr/bin/env bash
# ============================================================
#  build.sh  -  Build ctxr_tools binary for Linux / macOS
#  Run this once from the folder that contains main.py
# ============================================================
set -e

echo "Installing / upgrading PyInstaller..."
python3 -m pip install --upgrade pyinstaller pillow

echo ""
echo "Building ctxr_tools binary..."
python3 -m PyInstaller ctxr_tools.spec --clean

echo ""
echo "============================================================"
echo " Done!  Your binary is at:  dist/ctxr_tools"
echo " Run it with:               ./dist/ctxr_tools"
echo "============================================================"
