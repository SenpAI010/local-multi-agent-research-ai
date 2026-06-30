"""
Ollama vision model integration for screenshots and local images.
"""
import base64
import io
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from PIL import Image


class VisionAnalyzer:
    """Analyze screenshots/images with a local Ollama vision model."""

    def __init__(
        self,
        model: str = "qwen2.5vl:72b",
        fallback_model: str = "llama3.2-vision:90b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 180,
    ):
        self.model = model
        self.fallback_model = fallback_model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.chat_url = f"{self.base_url}/api/chat"

    def analyze_image(
        self,
        image: Image.Image,
        prompt: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze a PIL image with an Ollama vision-capable model."""
        selected_model = model or self.model
        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [self._image_to_base64(image)],
                }
            ],
            "stream": False,
        }

        try:
            response = requests.post(self.chat_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            message = data.get("message", {}) or {}
            return {
                "ok": True,
                "model": selected_model,
                "text": (message.get("content") or "").strip(),
            }
        except Exception as first_error:
            if selected_model == self.fallback_model:
                return {"ok": False, "error": str(first_error), "model": selected_model}

            try:
                return self.analyze_image(image, prompt, model=self.fallback_model)
            except Exception as second_error:
                return {
                    "ok": False,
                    "model": selected_model,
                    "error": f"{first_error}; fallback failed: {second_error}",
                }

    def analyze_file(self, path: Path, prompt: str) -> Dict[str, Any]:
        """Analyze an image file."""
        image = Image.open(path)
        return self.analyze_image(image, prompt)

    def _image_to_base64(self, image: Image.Image) -> str:
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")


__all__ = ["VisionAnalyzer"]
