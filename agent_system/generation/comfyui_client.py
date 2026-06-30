"""
Local ComfyUI client.

This does not install ComfyUI. It talks to a locally running ComfyUI server,
usually http://127.0.0.1:8188.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from urllib import request


class ComfyUIClient:
    """Minimal local ComfyUI API client."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188", output_dir: Optional[Path] = None):
        self.base_url = base_url.rstrip("/")
        self.output_dir = Path(output_dir or "./agent_sandbox/generated_images").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def health_check(self) -> Dict[str, Any]:
        try:
            with request.urlopen(f"{self.base_url}/system_stats", timeout=5) as response:
                return {"ok": True, "data": json.loads(response.read().decode("utf-8"))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def queue_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Queue a raw ComfyUI workflow JSON."""
        payload = json.dumps({"prompt": workflow}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                return {"ok": True, "data": json.loads(response.read().decode("utf-8"))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_prompt_request(self, prompt: str, negative: str = "", style: str = "flux") -> Dict[str, Any]:
        """Store a generation request for later ComfyUI workflow execution."""
        request_path = self.output_dir / f"request_{int(time.time())}.json"
        data = {
            "prompt": prompt,
            "negative": negative,
            "style": style,
            "status": "workflow_required",
            "note": "Attach a ComfyUI workflow template to execute this automatically.",
        }
        request_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "file": str(request_path), "message": "Generation request saved"}


__all__ = ["ComfyUIClient"]
