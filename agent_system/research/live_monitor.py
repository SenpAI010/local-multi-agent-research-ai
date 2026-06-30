"""Read-only localhost dashboard for a running research project."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional


HTML = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Live</title><style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151d31;--line:#2a3858;--text:#e8eefc;--muted:#9aabc8;--good:#51d88a;--warn:#ffc857;--bad:#ff6b6b;--accent:#79a7ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;background:#0b1020ee;border-bottom:1px solid var(--line);padding:14px 20px;z-index:2}h1{font-size:20px;margin:0}#stamp{color:var(--muted)}
main{padding:18px;display:grid;grid-template-columns:repeat(12,1fr);gap:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}.wide{grid-column:span 12}.half{grid-column:span 6}.third{grid-column:span 4}
h2{font-size:14px;color:var(--accent);margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em}.metric{font-size:24px;font-weight:700}.muted{color:var(--muted)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto;margin:0;background:#0b1020;padding:10px;border-radius:8px}.row{padding:7px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
@media(max-width:900px){.half,.third{grid-column:span 12}}
</style></head><body><header><h1 id="title">Research Live</h1><span id="stamp">verbinde…</span></header><main>
<section class="card third"><h2>Aktiver Ansatz</h2><div class="metric" id="approach">–</div><div class="muted" id="next">–</div></section>
<section class="card third"><h2>Fortschritt</h2><div class="metric" id="step">0</div><div class="muted" id="cycle">–</div></section>
<section class="card third"><h2>Artefakte</h2><div id="counts">–</div></section>
<section class="card half"><h2>Letzte Aktionen</h2><div id="trace"></div></section>
<section class="card half"><h2>Offene Lücken</h2><div id="gaps"></div></section>
<section class="card half"><h2>Lemmata / Lean</h2><div id="lemmas"></div></section>
<section class="card half"><h2>Claims</h2><div id="claims"></div></section>
<section class="card wide"><h2>LaTeX – letzter Stand</h2><pre id="latex"></pre></section>
</main><script nonce="research-live-monitor">
const esc=s=>String(s??'')
  .replaceAll('&','&amp;')
  .replaceAll('<','&lt;')
  .replaceAll('>','&gt;')
  .replaceAll('"','&quot;')
  .replaceAll("'","&#039;");
const txt=s=>String(s??'');
const rows=(xs,fn)=>xs.length?xs.map(fn).join(''):'<div class="muted">Noch nichts vorhanden.</div>';
async function refresh(){try{const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();
document.querySelector('#title').textContent='Research Live — '+txt(d.problem);document.querySelector('#stamp').textContent='Aktualisiert: '+new Date().toLocaleTimeString();
document.querySelector('#approach').textContent=txt(d.status.active_approach_id||'–');document.querySelector('#next').textContent=txt(d.status.next_action||d.checkpoint.next_planned_step||'–');
document.querySelector('#step').textContent=txt(d.checkpoint.last_completed_step||0);document.querySelector('#cycle').textContent='Autopilot: '+txt(d.autopilot.status||'idle')+' · Hintergrund: '+txt(d.background.status||'idle');
document.querySelector('#counts').innerHTML=`Claims: <b>${d.claims.length}</b><br>Lemmata: <b>${d.lemmas.length}</b><br>Quellen: <b>${d.sources.length}</b><br>Formal verifiziert: <b class="good">${d.lemmas.filter(x=>x.proof_status==='formally_verified').length}</b>`;
document.querySelector('#trace').innerHTML=rows(d.trace.slice().reverse(),x=>`<div class="row"><b>${esc(x.action)}</b> <span class="muted">${esc(x.approach_id||'')}</span><br>${esc(x.result)}</div>`);
document.querySelector('#gaps').innerHTML=rows(d.status.known_gaps||[],x=>`<div class="row warn">${esc(x)}</div>`);
document.querySelector('#lemmas').innerHTML=rows(d.lemmas,x=>`<div class="row"><b>${esc(x.lemma_id)}</b> <span class="${x.proof_status==='formally_verified'?'good':'warn'}">${esc(x.proof_status)}</span><br>${esc(x.title)}<br><span class="muted">${esc(x.conclusion)}</span></div>`);
document.querySelector('#claims').innerHTML=rows(d.claims.slice(-12),x=>`<div class="row"><b>${esc(x.claim_id)}</b> <span class="${x.status==='formally_verified'||x.status==='source_supported'?'good':'warn'}">${esc(x.status)}</span><br>${esc(x.text)}</div>`);
document.querySelector('#latex').textContent=txt(d.latex_tail);
}catch(e){document.querySelector('#stamp').textContent='Verbindung unterbrochen: '+e;}}
refresh();setInterval(refresh,1500);
</script></body></html>"""


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def project_snapshot(project_dir: Path) -> Dict[str, Any]:
    trace = []
    trace_path = project_dir / "trace.jsonl"
    if trace_path.exists():
        for line in trace_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
            try: trace.append(json.loads(line))
            except Exception: pass
    tex = project_dir / "main.tex"
    latex_lines = tex.read_text(encoding="utf-8", errors="replace").splitlines()[-100:] if tex.exists() else []
    status = _load(project_dir / "status.json", {})
    return {
        "problem": status.get("problem", project_dir.name),
        "status": status,
        "checkpoint": _load(project_dir / "checkpoint.json", {}),
        "autopilot": _load(project_dir / "autopilot_state.json", {}),
        "background": _load(project_dir / "background_research.json", {}),
        "claims": _load(project_dir / "claims.json", []),
        "lemmas": _load(project_dir / "formal_lemmas.json", []),
        "sources": _load(project_dir / "sources.json", []),
        "trace": trace,
        "latex_tail": "\n".join(latex_lines),
    }


class ResearchLiveMonitor:
    def __init__(self) -> None:
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.url = ""

    def start(self, project_dir: Path, port: int = 8766) -> str:
        if self.thread and self.thread.is_alive():
            return self.url
        project_dir = Path(project_dir).resolve()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/" or self.path.startswith("/?"):
                    body, kind = HTML.encode("utf-8"), "text/html; charset=utf-8"
                elif self.path == "/api/state":
                    body, kind = json.dumps(project_snapshot(project_dir), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"
                else:
                    self.send_error(404); return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'nonce-research-live-monitor'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_args: Any) -> None: pass

        self.server = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        self.thread = threading.Thread(target=self.server.serve_forever, name="research-live-monitor", daemon=True)
        self.thread.start()
        return self.url

    def stop(self) -> None:
        if self.server:
            self.server.shutdown(); self.server.server_close()
        self.server = None; self.thread = None; self.url = ""

    def status(self) -> Dict[str, Any]:
        return {"running": bool(self.thread and self.thread.is_alive()), "url": self.url, "bind": "127.0.0.1"}
