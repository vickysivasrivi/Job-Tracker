#!/bin/bash
cd "$(dirname "$0")"
if ! command -v node &>/dev/null; then
  echo "Node.js not found. Install from https://nodejs.org"; read; exit 1
fi
node server.js
