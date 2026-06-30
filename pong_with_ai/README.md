# Pong gegen deinen Agenten

Du spielst links als Umut. Der Agent spielt rechts.

## Start

Im Hauptordner:

```powershell
.\pong_with_ai\start_pong.ps1
```

Oder direkt diese Datei im Browser öffnen:

```text
pong_with_ai\index.html
```

## Steuerung

- `W` / `S`: dein linkes Paddle
- Maus hoch/runter: dein linkes Paddle
- `Leertaste`: Start/Pause
- `KI-Staerke`: wie gut der Agent rechts spielt

Standard: Der rechte Schlaeger nutzt schnelle Browser-KI.

Wenn du "Ollama spielt rechts" aktivierst, fragt das Spiel lokal `qwen3:30b`
ueber `127.0.0.1:11434`. Das Sprachmodell entscheidet dann `up`, `down` oder
`stay`. Wenn Ollama zu langsam ist, nutzt das Spiel kurz eine Fallback-Heuristik,
damit der Ball nicht einfriert.
