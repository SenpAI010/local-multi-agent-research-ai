# run_agent.ps1 (safe launcher)
# - checks Ollama listens ONLY on localhost addresses (127.0.0.1 and/or ::1)
# - checks firewall rule exists + enabled
# - checks Ollama API reachable
# - starts agent with venv python

$ErrorActionPreference = "SilentlyContinue"
$root = $PSScriptRoot

Write-Host "=== Local Agent Launcher ==="

# ---- 1) Check listener (must be localhost only) ----
$listeners = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $listeners) {
  Write-Host "ERROR: No listener on port 11434. Start Ollama first." -ForegroundColor Red
  Write-Host "Tip: ollama run qwen3-coder:30b" -ForegroundColor Yellow
  exit 2
}

# Force ARRAY (prevents string-index bug)
$addrs = @($listeners | Select-Object -ExpandProperty LocalAddress -Unique)
$allowed = @("127.0.0.1", "::1")
$bad = @($addrs | Where-Object { $allowed -notcontains $_ })

if ($bad.Count -gt 0) {
  Write-Host "ERROR: Ollama is NOT localhost-only!" -ForegroundColor Red
  Write-Host ("LocalAddress(es): " + ($addrs -join ", ")) -ForegroundColor Yellow
  Write-Host "Tip: netstat -ano | findstr :11434" -ForegroundColor Yellow
  exit 3
}

Write-Host ("OK: Ollama listens locally on: " + ($addrs -join ", ") + " (port 11434)") -ForegroundColor Green

# ---- 2) Check firewall rule ----
$ruleName = "Block Ollama Inbound 11434"
$rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $rule) {
  Write-Host ("WARN: Firewall rule not found: " + $ruleName) -ForegroundColor Yellow
} elseif ($rule.Enabled -eq "True" -and $rule.Direction -eq "Inbound" -and $rule.Action -eq "Block") {
  Write-Host "OK: Firewall rule active (inbound 11434 blocked)" -ForegroundColor Green
} else {
  Write-Host "WARN: Firewall rule exists but not as expected" -ForegroundColor Yellow
  Write-Host ("Enabled=" + $rule.Enabled + " Direction=" + $rule.Direction + " Action=" + $rule.Action) -ForegroundColor Yellow
}

# ---- 3) Check Ollama API reachable ----
try {
  Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
  Write-Host "OK: Ollama API reachable on 127.0.0.1:11434" -ForegroundColor Green
} catch {
  Write-Host "ERROR: Ollama API not reachable on 127.0.0.1:11434" -ForegroundColor Red
  Write-Host "Tip: start Ollama, then retry" -ForegroundColor Yellow
  exit 4
}

# ---- 4) Start agent ----
$venvPython = Join-Path $root ".venv_personal_agent\Scripts\python.exe"
$mainPy     = Join-Path $root "main_phase3.py"

if (Test-Path $venvPython) {
  $pythonExe = $venvPython
} else {
  $pythonExe = "python"
  Write-Host "WARN: .venv_personal_agent not found; using system Python from PATH." -ForegroundColor Yellow
  Write-Host "Tip: create a venv with: python -m venv .venv_personal_agent; .\.venv_personal_agent\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Yellow
}
if (-not (Test-Path $mainPy)) {
  Write-Host ("ERROR: main.py not found: " + $mainPy) -ForegroundColor Red
  exit 6
}

Write-Host "Starting agent..." -ForegroundColor Cyan
Set-Location $root
& $pythonExe $mainPy
