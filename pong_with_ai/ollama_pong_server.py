"""
Local Pong server with an Ollama-controlled right paddle.

The browser game calls /ai_move. This server asks a local Ollama language model
for a compact move decision: up, down, or stay.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:30b"
PORT = 8765


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def heuristic_move(state: dict) -> tuple[str, str]:
    ball = state.get("ball", {})
    ai = state.get("ai", {})
    field = state.get("field", {})
    paddle_height = float(field.get("paddleHeight", 104))
    ai_center = float(ai.get("center", 270))
    ball_y = float(ball.get("y", 270))
    ball_vx = float(ball.get("vx", 0))

    if ball_vx < 0:
        target = float(field.get("height", 540)) / 2
    else:
        target = ball_y

    deadzone = max(14.0, paddle_height * 0.12)
    if ai_center < target - deadzone:
        return "down", "Ball ist tiefer als mein Paddle."
    if ai_center > target + deadzone:
        return "up", "Ball ist hoeher als mein Paddle."
    return "stay", "Paddle ist nah genug am Ziel."


def ollama_move(state: dict) -> dict:
    prompt = (
        "Du spielst Pong als rechter Schlaeger. Antworte NUR als JSON, "
        'Format: {"move":"up|down|stay","reason":"max 8 words"}. '
        "Koordinaten: y=0 ist oben. Bewege dich zum Ball, wenn er nach rechts fliegt, "
        "sonst halte dich eher in der Mitte.\n\n"
        f"GAME_STATE={json.dumps(state, ensure_ascii=False)}"
    )
    payload = {
        "model": MODEL,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 28,
        },
        "messages": [
            {
                "role": "system",
                "content": "Du bist ein lokaler Pong-Spieler. Keine Erklaerung ausser JSON.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=2.8) as response:
        raw = response.read().decode("utf-8", errors="replace")
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    data = json.loads(raw)
    content = data.get("message", {}).get("content", "")
    parsed = _extract_json(content)
    move = parsed.get("move")
    if move not in {"up", "down", "stay"}:
        move, reason = heuristic_move(state)
        return {
            "move": move,
            "reason": f"Fallback: {reason}",
            "model": MODEL,
            "latency_ms": elapsed_ms,
        }
    return {
        "move": move,
        "reason": str(parsed.get("reason", "Modellentscheidung"))[:80],
        "model": MODEL,
        "latency_ms": elapsed_ms,
    }


class PongHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/ai_move":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            state = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._json({"move": "stay", "reason": "ungueltiger Zustand"}, status=400)
            return

        try:
            result = ollama_move(state)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            move, reason = heuristic_move(state)
            result = {
                "move": move,
                "reason": f"Heuristik, Ollama zu langsam: {reason}",
                "model": "fallback",
                "latency_ms": None,
            }

        self._json(result)

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), PongHandler)
    print(f"Pong server: http://127.0.0.1:{PORT}")
    print(f"Ollama model rechts: {MODEL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
