$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "ensure_update_tool.ps1")
Start-Process "http://127.0.0.1:8502"
