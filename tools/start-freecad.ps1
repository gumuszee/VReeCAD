<#
.SYNOPSIS
  Launch the installed FreeCAD GUI detached, then wait until the MCP RPC server answers (port 9875).
.PARAMETER Wait  Seconds to wait for RPC (default 90). Use 0 to skip waiting.
.PARAMETER XrRuntime  Optional path to an OpenXR runtime json (sets XR_RUNTIME_JSON for this launch).
#>
param([int]$Wait = 90, [string]$XrRuntime)
. "$PSScriptRoot\env.ps1"
if ($XrRuntime) { $env:XR_RUNTIME_JSON = $XrRuntime }
$log = "$LogDir\freecad-$(Get-Date -Format yyyyMMdd-HHmmss).log"
Start-Process -FilePath $FreeCADExe -ArgumentList @("--write-log", $log) -WorkingDirectory $ProjectRoot
"started FreeCAD (log: $log)"
if ($Wait -gt 0) {
    $deadline = (Get-Date).AddSeconds($Wait)
    while ((Get-Date) -lt $deadline) {
        if ((Test-NetConnection 127.0.0.1 -Port 9875 -WarningAction SilentlyContinue -InformationLevel Quiet)) { "RPC server is up on 127.0.0.1:9875"; return }
        Start-Sleep -Seconds 3
    }
    Write-Warning "RPC server did not come up within $Wait s - check FreeCAD Report view / log"
}
