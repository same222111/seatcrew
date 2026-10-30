#!/usr/bin/env bash
# Build dist/SeatCrew-<version>-x86_64.AppImage from the PyInstaller folder app.
#   bash packaging/build_appimage.sh            (runs PyInstaller first unless SKIP_PYINSTALLER=1)
# Needs: python with shared libpython (python.org / uv / actions/setup-python), pip install ".[desktop]" pyinstaller qtpy PyQt6 PyQt6-WebEngine
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
VER="$(python -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
DIST="${DIST:-$ROOT/dist}"; WORK="${WORK:-$ROOT/build}"
[ "${SKIP_PYINSTALLER:-0}" = 1 ] || pyinstaller packaging/seatcrew.spec --noconfirm --distpath "$DIST" --workpath "$WORK"
APPDIR="$WORK/SeatCrew.AppDir"; rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$DIST/SeatCrew" "$APPDIR/usr/lib-seatcrew"
cp packaging/seatcrew.desktop "$APPDIR/seatcrew.desktop"
cp packaging/icon.png "$APPDIR/seatcrew.png"; cp packaging/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/seatcrew.png"; ln -sf seatcrew.png "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
# Chromium sandbox needs user namespaces; many distros/containers lack them -> run without it (local pages only).
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---no-sandbox}"
exec "$HERE/usr/lib-seatcrew/SeatCrew" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL="${APPIMAGETOOL:-appimagetool}"
if ! command -v "$TOOL" >/dev/null; then
  TOOL="$WORK/appimagetool"; curl -sSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage; chmod +x "$TOOL"
fi
OUT="$DIST/SeatCrew-$VER-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT"
echo "built $OUT"
