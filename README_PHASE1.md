# Ollama Multi-Agent System (Phase 1)

Vollständig lokales, modulares KI-Agenten-System mit Ollama.

## 🏗️ Architektur

```
agent_system/
├── core/
│   ├── ollama_native.py        # Natives tools-Protokoll (NICHT Regex!)
│   ├── memory.py               # SQLite + User-Profil + Bestätigung
│   └── sandbox.py              # Path-Validierung
├── tools/
│   ├── workbench.py            # Python-Scripts, pip install
│   ├── web.py                  # DuckDuckGo, fetch
│   ├── system.py               # Commands (Allowlist)
│   └── __init__.py             # Note-Tools
├── agents/
│   └── __init__.py             # Orchestrator (Chef-Agent)
└── main.py                     # CLI Entry-Point
```

## 🚀 Quick Start

### 1. Ollama Setup (Windows)
```powershell
# Install: https://ollama.ai/download
ollama pull qwen2.5:7b-instruct
ollama pull deepseek-r1:32b  # Optional, später

# Starten (in separatem Terminal):
ollama serve
```

### 2. Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Agent
```bash
python main_new.py
```

First Run: System wird dich nach Profil fragen (Name, Rolle, Tech-Stack).

## 💡 Usage

### Interactive Mode
```
You: Hallo, wer bist du?
AI: [response]

You: Schreib mir ein "Hello World" Script
AI: [creates file, may run tools]
```

### Auto Mode (multiple tool calls)
```
You: /auto 10 "Installiere numpy und erstelle ein Skript"
```

## 🔧 Features (Phase 1)

✅ **Natives Tool-Calling**: Echtes Ollama `tools`-Protokoll, nicht Regex-Parsing
✅ **Modulare Architektur**: Einfach neue Tools hinzufügen
✅ **User-Profil**: Persistente Konfiguration (Name, Role, Tech-Stack)
✅ **Explizite Bestätigung**: Vor jedem Speicher/Command wird gefragt
✅ **SQLite Memory**: Long-term conversation history + summaries
✅ **Sandbox**: Workbench nur in `./agent_sandbox/workbench/`
✅ **Allowlist-Security**: Commands sehr eingeschränkt (git, python -c/m nur)

## 🛠️ Tools

### Workbench
- `wb_write_file`: Datei schreiben
- `wb_read_file`: Datei lesen
- `wb_run_python`: Script ausführen
- `wb_pip_install`: Paket installieren

### Web
- `web_search`: DuckDuckGo Suche
- `web_fetch`: URL fetchen (safe)

### System
- `run_command`: Shell (stark eingeschränkt, Allowlist)

### Notes
- `save_note`: Notiz speichern
- `list_notes`: Notizen auflisten

## 📝 Konfiguration

### User Profile (automatisch erstellt)
```json
{
  "name": "Dein Name",
  "role": "Masterstudent Mathematik",
  "tech_stack": {
    "ide": "VS Code",
    "languages": ["Python", "Julia"],
    "frameworks": ["ROS 2", "Gazebo"]
  }
}
```

### Memory
- `agent_sandbox/memory.sqlite3`: Alle Chats + Zusammenfassungen
- `agent_sandbox/user_profile.json`: User-Profil
- `agent_sandbox/notes/`: Gespeicherte Notizen
- `agent_sandbox/workbench/`: Python-Scripts & Venv

## 🔐 Sicherheit

✅ **Localhost-Only**: Ollama nur auf 127.0.0.1:11434
✅ **No Auto-Execution**: Jeder Command braucht [y/N]-Approval
✅ **Allowlist**: Nur whitelisted Commands erlaubt
✅ **Sandbox**: Alle Dateien in `./agent_sandbox/`
✅ **No Destructive Ops**: `rm`, `del`, `format`, etc. sind blockiert

## 🚦 Next Steps (Phase 2)

- Async Screenshot-Monitor (Pillow/OpenCV)
- OCR für Windows/Discord/Zoom
- Real-time Error Detection in IDE
- Integration mit VS Code (Diagnostics)

## 📞 Support

Falls Ollama nicht antwortet:
1. `ollama serve` läuft?
2. Model installiert? `ollama list`
3. Port 11434 offen? `curl http://localhost:11434/api/tags`

## 🎯 Design Principles

1. **Native Protocols**: Ollama tools, nicht RegEx-Parsing
2. **Modularity**: Einfach neue Tools/Agents hinzufügen
3. **Security-First**: Allowlists, Sandboxes, Approvals
4. **Transparency**: Alle Actions bestätigt, logging
5. **Extensibility**: Chef-Unterchef Pattern für Multi-Agenten
