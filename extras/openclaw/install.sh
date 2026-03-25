#!/bin/bash
# Install Lando skill into OpenClaw
# Usage: ./install.sh [openclaw_skills_dir]

SKILLS_DIR="${1:-$HOME/.openclaw/skills}"
SKILL_NAME="lando-telegram"

if [ ! -d "$SKILLS_DIR" ]; then
    echo "Error: OpenClaw skills directory not found at $SKILLS_DIR"
    echo "Usage: $0 /path/to/.openclaw/skills"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$SKILLS_DIR/$SKILL_NAME"
cp "$SCRIPT_DIR/SKILL.md" "$SKILLS_DIR/$SKILL_NAME/SKILL.md"

echo "Installed $SKILL_NAME to $SKILLS_DIR/$SKILL_NAME"
echo "Restart OpenClaw gateway to pick up the new skill."
