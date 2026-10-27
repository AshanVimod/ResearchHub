# Create a "Research Hub" shortcut that opens the app (no console window).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1                 (puts it on your Desktop)
#         powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1 -Folder "D:\Somewhere"
param([string]$Folder = [Environment]::GetFolderPath("Desktop"))

$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Run start.bat once first; $pythonw is missing." }

$link = Join-Path $Folder "Research Hub.lnk"
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pythonw
$s.Arguments = '"' + (Join-Path $root "scripts\launch.pyw") + '"'
$s.WorkingDirectory = $root
$s.IconLocation = (Join-Path $root "static\icon.ico") + ",0"
$s.Description = "Open Research Hub (starts it in the background if needed)"
$s.Save()
Write-Output "Created $link"
