$ErrorActionPreference = "Stop"
$dashboardRoot = Split-Path $PSScriptRoot -Parent
Start-Process -FilePath python `
    -ArgumentList @(
        "-m", "streamlit", "run", "local_update_tool.py",
        "--server.address", "127.0.0.1",
        "--server.port", "8502",
        "--server.headless", "true"
    ) `
    -WorkingDirectory $dashboardRoot `
    -WindowStyle Hidden
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8502"
