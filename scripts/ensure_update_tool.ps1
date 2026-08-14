param(
    [int]$Port = 8502
)

$ErrorActionPreference = "Stop"
$dashboardRoot = Split-Path $PSScriptRoot -Parent
$healthUrl = "http://127.0.0.1:$Port/"
$mutex = [System.Threading.Mutex]::new($false, "Local\AtlasAmazonImportTool8502")
$ownsMutex = $false

function Test-UpdateToolHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        exit 0
    }

    if (Test-UpdateToolHealth) {
        exit 0
    }

    $pythonCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    )
    $pythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $pythonPath) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $pythonPath = $pythonCommand.Source
        }
    }
    if (-not $pythonPath) {
        throw "Python was not found for the Atlas import tool."
    }

    Start-Process -FilePath $pythonPath `
        -ArgumentList @(
            "-m", "streamlit", "run", "local_update_tool.py",
            "--server.address", "127.0.0.1",
            "--server.port", "$Port",
            "--server.headless", "true"
        ) `
        -WorkingDirectory $dashboardRoot `
        -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(25)
    do {
        Start-Sleep -Milliseconds 750
        if (Test-UpdateToolHealth) {
            exit 0
        }
    } while ((Get-Date) -lt $deadline)

    throw "The Atlas import tool did not respond at $healthUrl after startup."
}
finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
