$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $here "ollama_pong_server.py"

if (-not (Test-Path $server)) {
    Write-Host "Pong-Server nicht gefunden: $server"
    exit 1
}

$python = Join-Path (Split-Path -Parent $here) ".venv_personal_agent\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Start-Process -WindowStyle Hidden -FilePath $python -ArgumentList @($server)
Start-Sleep -Seconds 1
Start-Process "http://127.0.0.1:8765/index.html"
