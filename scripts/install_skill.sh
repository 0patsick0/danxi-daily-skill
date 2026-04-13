#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$HOME/.agents/skills/danxi-daily}"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$TARGET_DIR"
rsync -a --delete \
  --exclude ".git" \
  --exclude "outputs" \
  "$SRC_DIR/" "$TARGET_DIR/"

echo "Installed danxi-daily skill to: $TARGET_DIR"
