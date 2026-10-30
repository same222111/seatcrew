#!/usr/bin/env bash
# SeatCrew installer for macOS and Linux - safe to re-run (upgrades in place).
#
#   curl -fsSL https://raw.githubusercontent.com/same222111/seatcrew/main/install.sh | bash
#   bash install.sh [--dry-run] [--source <git-url|path>] [--ref main] [--no-shortcut] [--no-desktop-app] [--launch]
#
# What it does (each step is printed; --dry-run prints them without changing anything):
#   1. finds Python >= 3.10
#   2. creates a private virtualenv in the app folder (no admin rights, nothing global)
#   3. pip-installs SeatCrew + the desktop window (pywebview; Qt WebEngine on Linux)
#   4. adds a launcher: Linux = app menu entry + Desktop icon (.desktop), macOS = ~/Applications/SeatCrew.app + Desktop alias
# Uninstall: delete the app folder and the two shortcuts printed at the end. Your data folder is kept.
set -euo pipefail
SOURCE="${SEATCREW_SOURCE:-git+https://github.com/same222111/seatcrew.git}"; REF="main"
DRY=0; SHORTCUT=1; DESKTOP_APP=1; LAUNCH=0; OS="$(uname -s)"
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --source) SOURCE="$2"; shift;; --ref) REF="$2"; shift;;
  --no-shortcut) SHORTCUT=0;; --no-desktop-app) DESKTOP_APP=0;; --launch) LAUNCH=1;;
  --os) OS="$2"; shift;;   # testing only: Linux | Darwin
  -h|--help) sed -n '2,15p' "$0"; exit 0;; *) echo "unknown option $1" >&2; exit 2;; esac; shift; done

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then echo "DRY-RUN: $*"; else "$@"; fi; }
write() { if [ "$DRY" = 1 ]; then echo "DRY-RUN: write $1"; else mkdir -p "$(dirname "$1")"; cat > "$1"; fi; }

case "$OS" in
  Darwin) APPDIR="$HOME/Library/Application Support/SeatCrew/app";;
  *)      APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/seatcrew/app";;
esac
VENV="$APPDIR/venv"; PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10+ not found. Install it first:" >&2
  [ "$OS" = Darwin ] && echo "  brew install python@3.12   (or https://www.python.org/downloads/)" >&2 || echo "  sudo apt install python3 python3-venv   (Fedora: sudo dnf install python3)" >&2
  exit 1
fi
case "$SOURCE" in git+*) SPEC="seatcrew[desktop] @ $SOURCE@$REF";; *) SPEC="$SOURCE[desktop]";; esac
EXTRA=(); [ "$OS" = Linux ] && EXTRA=(qtpy "PyQt6>=6.5" "PyQt6-WebEngine>=6.5")

say "1/4 Python: $PY ($("$PY" -V 2>&1))"
say "2/4 virtualenv: $VENV"
run mkdir -p "$APPDIR"
run "$PY" -m venv "$VENV"
say "3/4 installing $SPEC"
run "$VENV/bin/python" -m pip install --upgrade --quiet pip
run "$VENV/bin/python" -m pip install --upgrade --quiet "$SPEC" "${EXTRA[@]}"
LAUNCHER="$VENV/bin/seatcrew-desktop"
ICON_DIR="$APPDIR/icon"
run mkdir -p "$ICON_DIR"
if [ "$DRY" = 1 ]; then echo "DRY-RUN: copy package icons to $ICON_DIR"; else
  "$VENV/bin/python" -c "import seatcrew,shutil,pathlib,sys; a=pathlib.Path(seatcrew.__file__).parent/'assets'; [shutil.copy(a/f, sys.argv[1]) for f in ('icon.png','icon.icns')]" "$ICON_DIR"; fi

SHORTCUTS=()
if [ "$SHORTCUT" = 1 ]; then
  say "4/4 launcher shortcut"
  DESK="$HOME/Desktop"; command -v xdg-user-dir >/dev/null 2>&1 && DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$DESK")"
  if [ "$OS" = Darwin ]; then
    APP="$HOME/Applications/SeatCrew.app"
    run mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
    write "$APP/Contents/MacOS/SeatCrew" <<SH
#!/bin/sh
exec "$LAUNCHER" "\$@"
SH
    run chmod +x "$APP/Contents/MacOS/SeatCrew"
    run cp "$ICON_DIR/icon.icns" "$APP/Contents/Resources/SeatCrew.icns"
    write "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>CFBundleName</key><string>SeatCrew</string><key>CFBundleExecutable</key><string>SeatCrew</string>
<key>CFBundleIdentifier</key><string>io.github.seatcrew</string><key>CFBundleIconFile</key><string>SeatCrew</string><key>CFBundlePackageType</key><string>APPL</string></dict></plist>
PL
    SHORTCUTS+=("$APP")
    if [ "$DESKTOP_APP" = 1 ]; then run ln -sfn "$APP" "$DESK/SeatCrew.app"; SHORTCUTS+=("$DESK/SeatCrew.app"); fi
  else
    ENTRY="[Desktop Entry]
Type=Application
Name=SeatCrew
Comment=Multi-AI seat workflows with a check chain
Exec=\"$LAUNCHER\"
Icon=$ICON_DIR/icon.png
Terminal=false
Categories=Office;Development;"
    MENU="${XDG_DATA_HOME:-$HOME/.local/share}/applications/seatcrew.desktop"
    printf '%s\n' "$ENTRY" | write "$MENU"; run chmod +x "$MENU"; SHORTCUTS+=("$MENU")
    if [ "$DESKTOP_APP" = 1 ]; then
      run mkdir -p "$DESK"
      printf '%s\n' "$ENTRY" | write "$DESK/seatcrew.desktop"; run chmod +x "$DESK/seatcrew.desktop"
      if [ "$DRY" = 0 ] && command -v gio >/dev/null 2>&1; then gio set "$DESK/seatcrew.desktop" metadata::trusted true 2>/dev/null || true; fi
      SHORTCUTS+=("$DESK/seatcrew.desktop")
    fi
  fi
else say "4/4 shortcut skipped (--no-shortcut)"; fi

say "done. Launch: double-click SeatCrew on your desktop, or run: $LAUNCHER"
for s in "${SHORTCUTS[@]}"; do echo "  shortcut: $s"; done
echo "  command line: $VENV/bin/seatcrew list | run <workflow> | ui <workflow>"
echo "RESULT app_dir=$APPDIR launcher=$LAUNCHER shortcuts=${#SHORTCUTS[@]} dry_run=$DRY"
if [ "$LAUNCH" = 1 ] && [ "$DRY" = 0 ]; then nohup "$LAUNCHER" >/dev/null 2>&1 & fi
