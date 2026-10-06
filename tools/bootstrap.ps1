<#
.SYNOPSIS
  Reproduce the whole BlocksCAD dev environment on a fresh Windows machine (idempotent - safe to re-run).
.DESCRIPTION
  0. run it from a clone of https://github.com/gumuszee/BlocksCAD_VR (the repo root is the addon; remote 'upstream' = kwahoo2)
  1. clones the reference repos into refs\ (shallow)
  2. installs pyopenxr + PyOpenGL into FreeCAD's bundled Python
  3. installs uv (winget) and syncs the freecad-mcp environment
  4. links addons into FreeCAD's Mod dir (install-addons.ps1) and enables MCP RPC auto-start
  Prerequisites: git, winget, FreeCAD 1.1.x installed per-user (see env.ps1 for the expected path).
  After it: tools\start-freecad.ps1, then python tools\fc_rpc.py status
#>
. "$PSScriptRoot\env.ps1"
$ErrorActionPreference = "Stop"
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Clone($url, $dir, [switch]$Full) {
    if (Test-Path "$dir\.git") { "have  $dir"; return }
    $a = @("clone"); if (-not $Full) { $a += @("--depth", "1") }
    & git @a $url $dir 2>&1 | Out-Null
    "cloned $dir"
}

Step "reference repos"
New-Item -ItemType Directory -Force $RefsDir | Out-Null
Clone https://github.com/FreeCAD/FreeCAD                     "$RefsDir\FreeCAD"
Clone https://github.com/kwahoo2/freecad-xr-workbench        "$RefsDir\freecad-xr-workbench"
Clone https://github.com/icosa-foundation/open-blocks        "$RefsDir\open-blocks"
Clone https://github.com/neka-nat/freecad-mcp                "$RefsDir\freecad-mcp"

Step "git remotes"
if (-not (git -C $AddonDir remote | Select-String -SimpleMatch upstream)) {
    git -C $AddonDir remote add upstream https://github.com/kwahoo2/freecad-xr-workbench
    "added remote upstream"
} else { "have  remote upstream" }

Step "python deps in FreeCAD's bundled Python"
& $FreeCADPy -m pip install --quiet pyopenxr PyOpenGL

Step "uv + MCP server env"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    $env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" + [Environment]::GetEnvironmentVariable("Path","Machine")
}
uv sync --directory $McpRepoDir

Step "link addons into FreeCAD Mod dir"
& "$PSScriptRoot\install-addons.ps1"

Step "dev-only: MCP registration for Claude Code + RPC auto-start (not part of the addon)"
if (-not (Test-Path "$ProjectRoot\.mcp.json")) {
    '{"mcpServers":{"freecad":{"command":"uv","args":["--directory","refs/freecad-mcp","run","freecad-mcp","--only-text-feedback"]}}}' | Set-Content "$ProjectRoot\.mcp.json"
    "wrote .mcp.json (git-ignored)"
}
$cfg = "$FreeCADUserDir\freecad_mcp_settings.json"
if (-not (Test-Path $cfg)) {
    '{"remote_enabled": false, "allowed_ips": "127.0.0.1", "auto_start_rpc": true, "auth_token": ""}' | Set-Content $cfg
    "wrote $cfg"
} else { "have  $cfg" }

Write-Host "`nDone. Next: tools\start-freecad.ps1" -ForegroundColor Green
