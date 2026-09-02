#!/bin/bash
set -e
cd "$(dirname "$0")"
PYTHON="$(command -v python3)"
if [ -z "$PYTHON" ]; then echo "Python 3 is required."; exit 1; fi
"$PYTHON" -m pip install --user --upgrade pyinstaller
rm -rf build dist "PartyChat Accounting.spec"
"$PYTHON" -m PyInstaller --windowed --onedir --name "PartyChat Accounting" --osx-bundle-identifier "com.snayanam.partychataccounting" PartyChat_Accounting.py
rm -rf "$HOME/Desktop/PartyChat Accounting.app"
cp -R "dist/PartyChat Accounting.app" "$HOME/Desktop/PartyChat Accounting.app"
echo "Built: $HOME/Desktop/PartyChat Accounting.app"
open "$HOME/Desktop"
