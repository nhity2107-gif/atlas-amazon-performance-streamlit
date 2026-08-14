$ErrorActionPreference = "Continue"
$mutex = [System.Threading.Mutex]::new($false, "Local\AtlasAmazonImportToolWatchdog")
$ownsMutex = $false

try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        exit 0
    }

    while ($true) {
        try {
            & (Join-Path $PSScriptRoot "ensure_update_tool.ps1")
        }
        catch {
            # Retry on the next interval. The watchdog stays silent and hidden.
        }
        Start-Sleep -Seconds 60
    }
}
finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
