# Ollama Multi-Agent System - Quick Start (Phase 2)

## 📦 Aktuelle Struktur

```
agent_system/
├── core/
│   ├── ollama_native.py        ← Natives tool-calling
│   ├── memory.py               ← SQLite + User-Profil
│   ├── sandbox.py              ← Path-Validierung
│   └── multimodal.py           ← NEW: Screen-Awareness
├── tools/
│   ├── workbench.py            ← Python-Scripts
│   ├── web.py                  ← DuckDuckGo, fetch
│   ├── system.py               ← Commands (Allowlist)
│   └── __init__.py             ← Notes
├── observers/                  ← NEW: Screen-Aware Components
│   ├── screenshot_monitor.py   ← Async Screenshot
│   ├── window_tracker.py       ← Window Tracking
│   ├── ocr_engine.py           ← OCR (EasyOCR/Tesseract)
│   ├── error_detector.py       ← Error Recognition
│   └── __init__.py
├── agents/
│   └── __init__.py             ← Orchestrator (Chef-Agent)
└── main.py                     ← Phase 1 CLI
```

## 🚀 Quick Start

### 1. Prerequisites
```powershell
# Ollama installieren
# https://ollama.ai/download

# Model pullen
ollama pull qwen2.5:7b-instruct

# Dependencies
pip install -r requirements.txt
```

### 2. Starten (Phase 2 mit Screen-Awareness)

**Terminal 1: Ollama**
```powershell
ollama serve
```

**Terminal 2: Agent**
```bash
python main_phase2.py
```

### 3. Interagieren

```
You: /screenshot
📸 Screenshot taken: agent_sandbox/screenshots/screenshot_20260523_151005.png
   Window: Visual Studio Code [vs code]
   ✅ No errors detected

You: Schreib mir ein Hello World Script
AI: [creates file, runs tools]
```

## 🎯 Commands

| Befehl | Effekt |
|--------|--------|
| `/screenshot` | Screenshot + OCR + Error Detection |
| `/context` | Zeige visuellen Kontext |
| `/auto 10 "task"` | Auto-Mode mit bis zu 10 Tool-Aufrufen |
| `exit` / `quit` | Beende Agent |

## 🔭 Was ist neu (Phase 2)?

### Multimodal Integration
- **Screenshot Monitor**: Nimmt alle 3 Sekunden Screenshots
- **Window Tracker**: Überwacht aktive Fenster (VS Code, Discord, Zoom, etc.)
- **OCR Engine**: Extrahiert Text aus Screenshots
  - EasyOCR (am besten, braucht GPU)
  - Tesseract (gut, weniger ressourcenhungrig)
  - Fallback (funktioniert auch ohne)
- **Error Detector**: Erkennt Code-Fehler automatisch
  - SyntaxError, TypeError, ImportError
  - Typos (pring statt print)
  - Performance Warnings

### Context-Embedding
Jeder Prompt wird automatisch mit visuellem Kontext erweitert:

```
[VISUAL CONTEXT]
Active Window: VS Code [vs code]
Detected errors: SyntaxError on Line 12
Visible Text: def hello(x)...

[USER]
Warum funktioniert mein Code nicht?

[OLLAMA]
Ich sehe einen Syntax-Fehler...
```

## 📊 Architecture Flow

```
Ollama serve
    ↓
main_phase2.py (CLI)
    ↓
MultimodalAgent (Coordinator)
    ├─ Screenshot Monitor (Thread 1)
    ├─ Window Tracker (Thread 2)
    ├─ OCR Engine (async on demand)
    ├─ Error Detector (async on demand)
    └─ Context Store (shared)
    ↓
User Input
    ↓
Visual Context Extraction
    ↓
Input + Context → Orchestrator
    ↓
Chat with Ollama (natives tool-calling)
    ↓
Tool Execution (with approval)
    ↓
Response + Memory Storage
```

## 🔒 Sicherheit (wie Phase 1)

✅ **Locals-Only**: Ollama nur auf 127.0.0.1:11434
✅ **No Auto-Execution**: Jeder Command mit Bestätigung
✅ **Allowlist**: Nur whitelisted Commands
✅ **Sandbox**: Alles in `./agent_sandbox/`
✅ **Approval-Required**: Vor jedem Tool-Aufruf

## 💡 Beispiele

### Screenshot + Auto-Analysis
```
You: /screenshot
📸 Screenshot: 1920x1080 | VS Code | No errors
```

### Fehler-Erkennung
```
You: Hilf mir mit meinem Python-Code
[Agent sieht Screenshot mit SyntaxError]
AI: Ich habe einen Fehler in Zeile 12 erkannt...
```

### Context-Aware Assistance
```
You: Was sollte ich installieren?
[Agent weiß: Discord ist offen, Unity Editor läuft, VS Code aktiv]
AI: Basierend auf deinen offenen Anwendungen...
```

## 🛠️ Installation OCR Backends

Optional (System funktioniert auch ohne):

### EasyOCR (GPU, am besten)
```bash
pip install easyocr
# Beim ersten Mal: Modelle werden heruntergeladen (~150MB)
```

### Tesseract (CPU, leicht)
```bash
pip install pytesseract
# Windows: https://github.com/UB-Mannheim/tesseract/wiki
```

### Keine OCR
- System funktioniert auch ohne OCR
- Nur Text-basierte Error-Detection via Regex

## 📁 Neue Dateien (Phase 2)

| Datei | Zweck |
|-------|-------|
| `main_phase2.py` | NEW: Phase 2 CLI Entry-Point |
| `test_phase2.py` | NEW: Phase 2 Test-Suite |
| `PHASE2_SUMMARY.md` | NEW: Phase 2 Dokumentation |
| `agent_system/core/multimodal.py` | NEW: Multimodal Integration |
| `agent_system/observers/` | NEW: Screenshot, Window, OCR, Errors |

## 🔄 Phase Progression

- **Phase 1**: ✅ Native Tool-Calling + Modules
- **Phase 2**: ✅ Screen-Awareness (aktuell)
- **Phase 3**: 📋 Semantic Memory + RAG + Decision Logging
- **Phase 4**: 📋 Multi-Agenten (CrewAI/LangGraph)

## ❓ Troubleshooting

### Ollama nicht erreichbar?
```
Fehler: Cannot reach Ollama: HTTPConnectionPool...
Lösung: ollama serve in separatem Terminal starten
```

### OCR Backends nicht verfügbar?
```
⚠️  EasyOCR not available
⚠️  Tesseract not available
Lösung: Optional - System funktioniert auch ohne OCR
```

### Screenshot zu dunkel/leer?
```
Prüfe: Active Window ist minimiert?
Prüfe: Screenshot-Verzeichnis: agent_sandbox/screenshots/
```

## 📞 Support

- Phase 1 Docs: `README_PHASE1.md`
- Phase 1 Summary: `PHASE1_SUMMARY.md`
- Phase 2 Summary: `PHASE2_SUMMARY.md`
- Tests: `test_phase1.py`, `test_phase2.py`

---

**Viel Spaß mit Phase 2! 🚀**

Starten mit:
```bash
python main_phase2.py
```
