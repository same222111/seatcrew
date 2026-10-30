# Installing SeatCrew with an AI coding agent

This file is written **for the agent** (Codex, Claude Code, Cursor, Aider, ...). A person only has to paste this prompt:

```text
Install SeatCrew from https://github.com/same222111/seatcrew for me. Follow INSTALL_WITH_AI.md in that repo
exactly: run install.sh (macOS/Linux) or install.ps1 (Windows), check the result line, put a SeatCrew
launcher shortcut on my desktop, open it once to confirm the window appears, then tell me what you did.
Do not ask me for API keys - SeatCrew works without them.
```

中文:
```text
请从 https://github.com/same222111/seatcrew 帮我安装 SeatCrew,严格按照仓库里的 INSTALL_WITH_AI.md 操作,
在我的桌面放一个 SeatCrew 快捷方式,打开一次确认窗口出现,然后告诉我你做了什么。不要向我要 API 密钥。
```

---

## Rules for the agent
1. **Use the scripts.** `install.sh` / `install.ps1` are the supported path. They are idempotent (safe to re-run = upgrade) and need **no admin/sudo** - everything goes into a per-user folder.
2. **Preview first.** Run with `--dry-run` / `-DryRun` and show the user the plan (it changes nothing), then run for real.
3. **Success = the last line** starts with `RESULT` and says `shortcuts=2 dry_run=0`. Report the `launcher=` path and the shortcut paths.
4. **Never** ask for, print, or commit API keys. AI keys are optional; the user enters them in the app's first-run wizard (stored in the user's data folder `.env`, file mode 600).
5. If Python 3.10+ is missing, install it as shown below (that is the only step that may need the user's password/confirmation) and re-run.
6. Do not install system-wide, do not use `sudo pip`, do not edit shell profiles.

## Step by step

### macOS
```bash
python3 --version                       # need >= 3.10; else: brew install python@3.12  (or python.org installer)
curl -fsSL https://raw.githubusercontent.com/same222111/seatcrew/main/install.sh -o /tmp/seatcrew-install.sh
bash /tmp/seatcrew-install.sh --dry-run # show the plan
bash /tmp/seatcrew-install.sh           # do it
open ~/Applications/SeatCrew.app        # confirm the window opens, then let the user close it
```
Creates `~/Applications/SeatCrew.app` and a Desktop alias `~/Desktop/SeatCrew.app`. App code: `~/Library/Application Support/SeatCrew/app`.

### Linux
```bash
python3 --version                       # need >= 3.10 and venv: sudo apt install python3 python3-venv  (Fedora: sudo dnf install python3)
curl -fsSL https://raw.githubusercontent.com/same222111/seatcrew/main/install.sh -o /tmp/seatcrew-install.sh
bash /tmp/seatcrew-install.sh --dry-run
bash /tmp/seatcrew-install.sh --launch  # installs, then opens the app once
```
Creates `~/.local/share/applications/seatcrew.desktop` (app menu) and `~/Desktop/seatcrew.desktop` (some desktops ask "Trust and launch" on first double-click). The window uses Qt WebEngine, installed into the private venv. If no window appears on a minimal system, install `libxkbcommon-x11-0 libxcb-cursor0 libegl1` (Debian/Ubuntu) and try again, or use the AppImage from Releases.

### Windows (PowerShell)
```powershell
py -3 --version                          # need >= 3.10; else: winget install -e --id Python.Python.3.12
irm https://raw.githubusercontent.com/same222111/seatcrew/main/install.ps1 -OutFile $env:TEMP\seatcrew-install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\seatcrew-install.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File $env:TEMP\seatcrew-install.ps1 -Launch
```
Creates `Desktop\SeatCrew.lnk` and a Start-menu entry. App code: `%LOCALAPPDATA%\SeatCrew\app`. The window uses Edge WebView2 (preinstalled on Windows 10/11).

### Already cloned the repo?
Use the local copy instead of GitHub: `bash install.sh --source .` / `install.ps1 -Source .`

## Options
| install.sh | install.ps1 | meaning |
|---|---|---|
| `--dry-run` | `-DryRun` | print every step, change nothing |
| `--source <git-url or path>` | `-Source` | install from a fork, branch URL or local folder |
| `--ref <tag/branch>` | `-Ref` | git ref (default `main`) |
| `--no-shortcut` | `-NoShortcut` | skip shortcuts |
| `--no-desktop-app` | - | app menu entry only, no Desktop icon (macOS/Linux) |
| `--launch` | `-Launch` | open the app when done |

## Verify (agent checklist)
- [ ] `RESULT ... shortcuts=2 dry_run=0` printed
- [ ] the desktop shortcut file exists
- [ ] `<venv>/bin/seatcrew list` (Windows: `<venv>\Scripts\seatcrew.exe list`) prints `content_review support_triage trading`
- [ ] the app window opened (first-run wizard: language, optional AI key)

Headless check without a window: `<launcher> --no-window --smoke 3` prints `url: http://127.0.0.1:<port>` and `stopped`.

## Where things live
| | Windows | macOS | Linux |
|---|---|---|---|
| program (venv) | `%LOCALAPPDATA%\SeatCrew\app` | `~/Library/Application Support/SeatCrew/app` | `~/.local/share/seatcrew/app` |
| your data (config, state, `.env`, own workflows) | `%APPDATA%\SeatCrew` | `~/Library/Application Support/SeatCrew` | `~/.local/share/seatcrew` |

**Data folder:** if the user wants their data somewhere else (e.g. `D:\\SeatCrewData`), they can pick it in the first-run wizard or with *Change data folder* on the home screen, or you can set `SEATCREW_DATA_DIR`. On Windows the installer also lets them choose the install folder (no admin needed).

**Uninstall:** delete the program folder and the shortcuts. Delete the data folder too if you want to remove settings and keys.
