#!/usr/bin/env bash
# macOS: dist/SeatCrew.app + dist/SeatCrew-<version>-macos.dmg (unsigned; first open = right-click > Open).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
VER="$(python -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
pyinstaller packaging/seatcrew.spec --noconfirm --distpath dist --workpath build
STAGE=build/dmg; rm -rf "$STAGE"; mkdir -p "$STAGE"; cp -R dist/SeatCrew.app "$STAGE/"; ln -s /Applications "$STAGE/Applications"
hdiutil create -volname SeatCrew -srcfolder "$STAGE" -ov -format UDZO "dist/SeatCrew-$VER-macos.dmg"
echo "built dist/SeatCrew-$VER-macos.dmg"
