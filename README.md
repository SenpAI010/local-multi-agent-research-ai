# Local Multi-Agent Research AI

Ein lokaler Ollama-basierter Multi-Agent-Assistent mit RAG, Screen-Awareness und einem experimentellen Research-Modus für formale mathematische Arbeit.

Der Research-Modus ist bewusst konservativ gebaut: Er darf Hypothesen, Lemmas, Experimente und Beweisversuche erzeugen, aber ein Claim gilt erst dann als formal bewiesen, wenn ein unabhängiger Prüfer wie Lean 4 ein Beweisartefakt erfolgreich kompiliert.

## Was enthalten ist

- Lokaler CLI-Agent über `main_phase3.py`
- Ollama-Anbindung mit Rollen für Chef-, Reasoning-, Coding- und Vision-Modelle
- Lokaler Sandbox-Workspace für Agent-Aktionen
- RAG-/Memory-Komponenten
- Screen-/OCR-/Vision-Beobachtung
- Research-Modus mit:
  - Hypothesen- und Lemma-Verwaltung
  - Claim-/Source-Prüfung
  - numerischen Experimenten
  - Lean-4-Verifikationsschnittstelle
  - Live-Monitor im Browser
  - LaTeX-/Markdown-Protokollierung

## Wichtige Sicherheitshinweise

- Ollama sollte nur lokal auf `127.0.0.1:11434` lauschen.
- `run_agent.ps1` prüft vor dem Start, ob Ollama lokal erreichbar ist.
- Der Ordner `agent_sandbox/` enthält lokale Laufdaten, Memory-Datenbanken, Screenshots, Research-Artefakte und potenziell private Daten. Er ist absichtlich in `.gitignore`.
- Der Agent darf mathematische Vermutungen untersuchen, aber er soll keinen Gesamtbeweis behaupten, solange kein vollständig formal verifiziertes Beweisartefakt existiert.

## Voraussetzungen

- Windows / PowerShell
- Python 3.11 oder neuer empfohlen
- [Ollama](https://ollama.com/)
- Optional für formale Beweise: Lean 4 über Elan

Beispielmodelle, die im Projekt vorkonfiguriert sind:

```powershell
ollama pull qwen3:30b
ollama pull deepseek-r1:70b
ollama pull qwen3-coder:30b
ollama pull llama3.2-vision:90b
```

Du kannst kleinere Modelle über Umgebungsvariablen verwenden, siehe `.env.example`.

## Installation

```powershell
cd "C:\Pfad\zum\Projekt"
python -m venv .venv_personal_agent
.\.venv_personal_agent\Scripts\python.exe -m pip install --upgrade pip
.\.venv_personal_agent\Scripts\python.exe -m pip install -r requirements.txt
```

Optional Lean 4 prüfen:

```powershell
$env:Path = "$env:USERPROFILE\.elan\bin;$env:Path"
lean --version
lake --version
```

## Start

Ollama starten:

```powershell
Start-Process -WindowStyle Hidden -FilePath "ollama" -ArgumentList @("serve")
```

Agent starten:

```powershell
cd "C:\Pfad\zum\Projekt"
.\run_agent.ps1
```

## Research-Modus Beispiel

Im Agenten-Prompt:

```text
/research_start "Untersuche die Riemannsche Vermutung. Entwickle und teste Hypothesen, suche Gegenbeispiele und versuche Teilresultate mit Lean und Mathlib formal zu beweisen. Verwerfe Platzhalter-Lemmata. Behaupte keinen Gesamtbeweis ohne vollständige formale Verifikation."
/research_web_on
/research_live_start
/research_background_start 100 120
```

Live-Monitor:

```text
http://127.0.0.1:8766/
```

Status prüfen:

```text
/research_background_status
/research_autopilot_plan
/research_autopilot_report
/research_trace
```

## Research-Artefakte

Während der Laufzeit erzeugt der Agent Daten unter:

```text
agent_sandbox/research/<projekt_name>/
```

Typische Dateien:

- `main.tex`
- `status.json`
- `checkpoint.json`
- `trace.jsonl`
- `reports/research_report.md`
- `reports/research_report.json`

Diese Dateien sind lokale Laufartefakte und werden standardmäßig nicht ins Repository aufgenommen.

## Tests

```powershell
.\.venv_personal_agent\Scripts\python.exe -m py_compile agent_system\research\manager.py
.\.venv_personal_agent\Scripts\python.exe -X utf8 test_research_mode.py
.\.venv_personal_agent\Scripts\python.exe -X utf8 test_research_infrastructure.py
```

## Repository-Hinweis

Nicht hochladen:

- virtuelle Umgebungen (`.venv*`)
- `agent_sandbox/`
- lokale Memory-Datenbanken
- Screenshots / OCR-Daten
- generierte PDFs / LaTeX-Aux-Dateien
- persönliche `.env`-Dateien
