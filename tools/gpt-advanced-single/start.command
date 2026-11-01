#!/bin/zsh
set -e
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
exec python3 app.py
