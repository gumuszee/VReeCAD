<#
.SYNOPSIS
  Link the addon (this repo) into FreeCAD's user Mod directory with a directory junction,
  so edits are live after a FreeCAD restart (no copying).
.DESCRIPTION
  Mod\BlocksCAD  -> <repo root>                       the addon itself
  Mod\FreeCADMCP -> refs\freecad-mcp\addon\FreeCADMCP  DEV-ONLY remote-control channel for tools\fc_rpc.py
                                                       (third-party addon; BlocksCAD never depends on it). Skip with -NoDevControl.
  Junctions need no admin rights. Re-running is safe (existing links are kept).
  -Remove unlinks (never deletes targets), including the link names "BlocksCAD-XR" and "BloCADVR-XR".
#>
param([switch]$Remove, [switch]$NoDevControl)
. "$PSScriptRoot\env.ps1"

$links = [ordered]@{ "BlocksCAD" = $AddonDir }
if (-not $NoDevControl) { $links["FreeCADMCP"] = $McpAddonDir }
New-Item -ItemType Directory -Force $FreeCADModDir | Out-Null

if ($Remove) {
    foreach ($name in @($links.Keys) + @("BlocksCAD-XR", "BloCADVR-XR")) {
        $link = Join-Path $FreeCADModDir $name
        if (Test-Path $link) { (Get-Item $link).Delete(); "removed $link" }
    }
    return
}
foreach ($name in $links.Keys) {
    $link = Join-Path $FreeCADModDir $name
    $target = $links[$name]
    if (-not (Test-Path $target)) { Write-Warning "target missing: $target"; continue }
    if (Test-Path $link) { "exists  $link"; continue }
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    "linked  $link -> $target"
}
