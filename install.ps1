<#
SeatCrew installer for Windows (PowerShell 5+). Safe to re-run (upgrades in place). No admin rights needed.

  irm https://raw.githubusercontent.com/same222111/seatcrew/main/install.ps1 | iex
  powershell -ExecutionPolicy Bypass -File install.ps1 [-DryRun] [-Source <git-url|path>] [-Ref main] [-NoShortcut] [-Launch]

Steps: 1) find Python 3.10+ (offers winget)  2) private venv in %LOCALAPPDATA%\SeatCrew\app
       3) pip install SeatCrew + desktop window (pywebview / Edge WebView2)  4) Desktop + Start-menu shortcuts
Uninstall: delete %LOCALAPPDATA%\SeatCrew\app and the two shortcuts. Your data (%APPDATA%\SeatCrew) is kept.
#>
param([switch]$DryRun, [string]$Source = $(if ($env:SEATCREW_SOURCE) { $env:SEATCREW_SOURCE } else { "git+https://github.com/same222111/seatcrew.git" }),
      [string]$Ref = "main", [switch]$NoShortcut, [switch]$Launch)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "==> $m" -ForegroundColor Green }
function Run([scriptblock]$b, [string]$desc) { if ($DryRun) { Write-Host "DRY-RUN: $desc" } else { & $b; if ($LASTEXITCODE) { throw "failed: $desc" } } }

$AppDir = Join-Path $env:LOCALAPPDATA "SeatCrew\app"; $Venv = Join-Path $AppDir "venv"
$Py = $null
foreach ($c in @("py -3.13", "py -3.12", "py -3.11", "py -3.10", "python")) {
  $exe, $arg = $c.Split(" ", 2)
  if (Get-Command $exe -ErrorAction SilentlyContinue) {
    $ok = & $exe @($arg | Where-Object { $_ }) -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
    if ($ok -eq "True") { $Py = @($exe) + @($arg | Where-Object { $_ }); break }
  }
}
if (-not $Py) {
  Write-Host "Python 3.10+ not found. Install it with:  winget install -e --id Python.Python.3.12   (or https://www.python.org/downloads/ - tick 'Add to PATH')" -ForegroundColor Yellow
  if (-not $DryRun) { exit 1 } else { $Py = @("python") }
}
$Spec = if ($Source -like "git+*") { "seatcrew[desktop] @ $Source@$Ref" } else { "$Source[desktop]" }

Say "1/4 Python: $($Py -join ' ')"
Say "2/4 virtualenv: $Venv"
Run { New-Item -ItemType Directory -Force -Path $AppDir | Out-Null } "mkdir $AppDir"
Run { & $Py[0] @($Py | Select-Object -Skip 1) -m venv $Venv } "$($Py -join ' ') -m venv $Venv"
$VPy = Join-Path $Venv "Scripts\python.exe"; $VPyw = Join-Path $Venv "Scripts\pythonw.exe"
Say "3/4 installing $Spec"
Run { & $VPy -m pip install --upgrade --quiet pip } "$VPy -m pip install --upgrade pip"
Run { & $VPy -m pip install --upgrade --quiet $Spec } "$VPy -m pip install --upgrade $Spec"
$Icon = Join-Path $AppDir "icon.ico"
Run { & $VPy -c "import seatcrew,shutil,pathlib,sys; shutil.copy(pathlib.Path(seatcrew.__file__).parent/'assets'/'icon.ico', sys.argv[1])" $Icon } "copy icon to $Icon"

$Shortcuts = @()
if (-not $NoShortcut) {
  Say "4/4 shortcuts"
  $Desk = [Environment]::GetFolderPath("Desktop"); if (-not $Desk) { $Desk = Join-Path $HOME "Desktop" }
  $Progs = [Environment]::GetFolderPath("Programs"); if (-not $Progs) { $Progs = Join-Path $HOME "Start Menu/Programs" }
  $targets = @((Join-Path $Desk "SeatCrew.lnk"), (Join-Path $Progs "SeatCrew.lnk"))
  foreach ($lnk in $targets) {
    if ($DryRun) { Write-Host "DRY-RUN: shortcut $lnk -> $VPyw -m seatcrew.desktop" }
    else {
      $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
      $s.TargetPath = $VPyw; $s.Arguments = "-m seatcrew.desktop"; $s.IconLocation = $Icon
      $s.WorkingDirectory = $AppDir; $s.Description = "SeatCrew"; $s.Save()
    }
    $Shortcuts += $lnk
  }
} else { Say "4/4 shortcut skipped (-NoShortcut)" }

Say "done. Double-click SeatCrew on your desktop."
$Shortcuts | ForEach-Object { Write-Host "  shortcut: $_" }
Write-Host "  command line: $(Join-Path $Venv 'Scripts\seatcrew.exe') list | run <workflow> | ui <workflow>"
Write-Host "RESULT app_dir=$AppDir launcher=$VPyw shortcuts=$($Shortcuts.Count) dry_run=$([int][bool]$DryRun)"
if ($Launch -and -not $DryRun) { Start-Process $VPyw -ArgumentList "-m", "seatcrew.desktop" }
