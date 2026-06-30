"""
Local video generation placeholder client.

Video generation models are usually driven through ComfyUI workflows. This
client stores requests and provides a stable future interface.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional


class VideoGenerationClient:
    """Store and route future local video generation jobs."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or "./agent_sandbox/generated_videos").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_request(
        self,
        prompt: str,
        duration_sec: int = 4,
        fps: int = 16,
        style: str = "local-video-workflow",
    ) -> Dict[str, Any]:
        path = self.output_dir / f"video_request_{int(time.time())}.json"
        data = {
            "prompt": prompt,
            "duration_sec": duration_sec,
            "fps": fps,
            "style": style,
            "status": "workflow_required",
            "note": "Use ComfyUI video workflow integration to execute.",
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "file": str(path)}


__all__ = ["VideoGenerationClient"]
