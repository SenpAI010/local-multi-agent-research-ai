# Datei: run_agent.ps1
# Zweck: 1) Safety-Check (Ollama local + Firewall) 2) Startet deinen Python-Agent in der venv

$ErrorActionPreference = "SilentlyContinue"

$projectRoot = "C:\Users\Inci\Desktop\Ki_Agent_für_alles"
$checkScript = Join-Path $projectRoot "check_ollama.ps1"
$pythonExe   = Join-Path $projectRoot ".venv_personal_agent\Scripts\python.exe"
$mainPy      = Join-Path $projectRoot "Main\main.py"

Write-Host "=== Run Local Agent ===" -ForegroundColor Cyan

# --- 0) Basic existence checks ---
if (-not (Test-Path $checkScript)) {
  Write-Host "❌ check_ollama.ps1 nicht gefunden: $checkScript" -ForegroundColor Red
  exit 1
}
if (-not (Test-Path $pythonExe)) {
  Write-Host "❌ Python venv nicht gefunden: $pythonExe" -ForegroundColor Red
  Write-Host "   Tipp: Prüfe ob .venv_personal_agent existiert." -ForegroundColor Yellow
  exit 1
}
if (-not (Test-Path $mainPy)) {
  Write-Host "❌ main.py nicht gefunden: $mainPy" -ForegroundColor Red
  exit 1
}

# --- 1) Run safety check ---
Write-Host "`n[1/2] Safety Check..." -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File $checkScript
if ($LASTEXITCODE -ne 0) {
  Write-Host "⚠️ Safety-Check meldet Probleme (ExitCode=$LASTEXITCODE). Starte Agent NICHT automatisch." -ForegroundColor Yellow
  Write-Host "   Wenn du trotzdem starten willst, öffne main.py manuell." -ForegroundColor Yellow
  exit 2
}

# --- 2) Ensure Ollama is reachable (hard gate) ---
try {
  $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
} catch {
  Write-Host "❌ Ollama API nicht erreichbar auf 127.0.0.1:11434. Starte zuerst Ollama." -ForegroundColor Red
  Write-Host "   Tipp: ollama run qwen2.5:7b-instruct" -ForegroundColor Yellow
  exit 3
}

# --- 3) Start agent ---
Write-Host "`n[2/2] Starte Agent..." -ForegroundColor Cyan
Set-Location $projectRoot
& $pythonExe $mainPy

Write-Host "`nAgent beendet." -ForegroundColor Cyan
