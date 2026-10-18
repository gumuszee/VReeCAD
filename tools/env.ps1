# Shared paths for all VReeCAD tools. Dot-source it:  . "$PSScriptRoot\env.ps1"
# Override any value by setting the same-named environment variable first.

$script:ProjectRoot = Split-Path -Parent $PSScriptRoot

# FreeCAD installation (the installed release, NOT a source build)
$script:FreeCADRoot = if ($env:BLOCADVR_FREECAD) { $env:BLOCADVR_FREECAD } else { "$env:LOCALAPPDATA\Programs\FreeCAD 1.1" }
$script:FreeCADExe  = "$FreeCADRoot\bin\freecad.exe"      # GUI
$script:FreeCADCmd  = "$FreeCADRoot\bin\freecadcmd.exe"   # headless console
$script:FreeCADPy   = "$FreeCADRoot\bin\python.exe"       # bundled Python 3.11 (has FreeCAD libs on path)

# Per-user FreeCAD data (FreeCAD 1.1 uses a versioned dir)
$script:FreeCADUserDir = "$env:APPDATA\FreeCAD\v1-1"
$script:FreeCADModDir  = "$FreeCADUserDir\Mod"

# Project layout
$script:AddonDir   = $ProjectRoot                                          # this repo IS the addon (fork of freecad-xr-workbench)
# DEV-ONLY remote-control channel (third-party freecad-mcp RPC addon); the VReeCAD addon never depends on it
$script:McpAddonDir = "$ProjectRoot\refs\freecad-mcp\addon\FreeCADMCP"
$script:McpRepoDir  = "$ProjectRoot\refs\freecad-mcp"                      # MCP server (run with uv)
$script:RefsDir    = "$ProjectRoot\refs"
$script:LogDir     = "$ProjectRoot\tools\logs"
