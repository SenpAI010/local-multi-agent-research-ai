"""
Optional local audio listener for meeting/Discord summaries.

This module is off by default and starts only after an explicit CLI command.
It records short chunks from a selected Windows input device and transcribes
them locally when faster-whisper is installed.
"""
import tempfile
import os
import threading
import time
import wave
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable


@dataclass
class AudioTranscript:
    timestamp: float
    text: str
    source: str


class AudioListener:
    """Record and transcribe audio chunks from a microphone/loopback device."""

    def __init__(
        self,
        sandbox_dir: Path,
        model_name: str = "base",
        sample_rate: int = 16000,
        chunk_seconds: int = 4,
        device: Optional[int] = None,
        source_provider: Optional[Callable[[], str]] = None,
    ):
        self.sandbox_dir = Path(sandbox_dir)
        self.audio_dir = self.sandbox_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        session_name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.session_dir = self.audio_dir / "temp_sessions" / session_name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.session_dir / "transcript.txt"
        self.model_name = model_name
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.device = device
        self.source_provider = source_provider

        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.transcripts: List[AudioTranscript] = []
        self._model = None
        self._last_error = ""
        self.live_print = False
        self.keep_wav = os.environ.get("LOCAL_AGENT_KEEP_AUDIO_WAV", "0") == "1"

    def dependency_status(self) -> Dict[str, Any]:
        missing = []
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            missing.append("sounddevice")

        try:
            import numpy  # noqa: F401
        except ImportError:
            missing.append("numpy")

        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            missing.append("faster-whisper")

        return {"ok": not missing, "missing": missing}

    def list_devices(self) -> Dict[str, Any]:
        status = self.dependency_status()
        if "sounddevice" in status["missing"]:
            return {"ok": False, "error": "sounddevice is not installed"}

        import sounddevice as sd

        devices = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append({
                    "index": idx,
                    "name": dev.get("name", ""),
                    "inputs": dev.get("max_input_channels", 0),
                    "default_samplerate": dev.get("default_samplerate", 0),
                })
        return {"ok": True, "devices": devices}

    def start(self, device: Optional[int] = None, live_print: bool = False) -> Dict[str, Any]:
        status = self.dependency_status()
        if not status["ok"]:
            return {
                "ok": False,
                "error": "Missing audio dependencies",
                "missing": status["missing"],
            }

        if self.is_running:
            return {"ok": True, "message": "Audio listener already running"}

        if device is not None:
            self.device = device

        self.live_print = live_print
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return {"ok": True, "message": "Audio listener started", "device": self.device}

    def stop(self) -> Dict[str, Any]:
        self.is_running = False
        self.live_print = False
        if self.thread:
            self.thread.join(timeout=max(2, self.chunk_seconds + 2))
        return {"ok": True, "message": "Audio listener stopped", "transcripts": len(self.transcripts)}

    def get_transcript_text(self, limit_chars: int = 6000) -> str:
        text = "\n".join(t.text for t in self.transcripts if t.text.strip())
        if len(text) > limit_chars:
            return text[-limit_chars:]
        return text

    def clear(self) -> None:
        self.transcripts.clear()
        try:
            self.transcript_path.write_text("", encoding="utf-8")
        except Exception:
            pass

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "device": self.device,
            "transcripts": len(self.transcripts),
            "last_error": self._last_error,
        }

    def measure_level(self, device: Optional[int] = None, seconds: float = 3.0) -> Dict[str, Any]:
        """Measure raw input level without Whisper to find the right device."""
        status = self.dependency_status()
        if "sounddevice" in status["missing"] or "numpy" in status["missing"]:
            return {"ok": False, "error": "sounddevice/numpy is not installed"}

        import numpy as np
        import sounddevice as sd

        dev = self.device if device is None else device
        try:
            samplerate = self._device_samplerate(dev)
            frames = sd.rec(
                int(seconds * samplerate),
                samplerate=samplerate,
                channels=1,
                dtype="float32",
                device=dev,
            )
            sd.wait()
        except Exception as e:
            return {"ok": False, "device": dev, "error": str(e)}

        arr = np.asarray(frames).reshape(-1)
        rms = float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        return {
            "ok": True,
            "device": dev,
            "seconds": seconds,
            "rms": rms,
            "peak": peak,
            "has_signal": peak > 0.01 or rms > 0.003,
        }

    def _load_model(self):
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel

        self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        return self._model

    def _run_loop(self) -> None:
        while self.is_running:
            try:
                wav_path = self._record_chunk()
                if not self.is_running:
                    if not self.keep_wav:
                        try:
                            wav_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                    break
                text = self._transcribe(wav_path)
                if not self.keep_wav:
                    try:
                        wav_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                if text:
                    source = self._source_label()
                    self._add_transcript(AudioTranscript(time.time(), text, source))
                    if self.live_print:
                        print(f"\n[LIVE TRANSCRIPT - {source}] {text}\nYou: ", end="", flush=True)
            except Exception as e:
                self._last_error = str(e)
                time.sleep(1)

    def _record_chunk(self) -> Path:
        import numpy as np
        import sounddevice as sd

        samplerate = self._device_samplerate(self.device)
        frames = sd.rec(
            int(self.chunk_seconds * samplerate),
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            device=self.device,
        )
        sd.wait()

        filepath = self.audio_dir / f"audio_{int(time.time())}.wav"
        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(np.asarray(frames).tobytes())
        return filepath

    def _transcribe(self, wav_path: Path) -> str:
        model = self._load_model()
        segments, _ = model.transcribe(str(wav_path), language="de", vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()

    def _source_label(self) -> str:
        parts = []
        if self.device is not None:
            parts.append(f"device {self.device}")
        if self.source_provider:
            try:
                window = self.source_provider()
                if window:
                    parts.append(window)
            except Exception:
                pass
        return " | ".join(parts) if parts else "audio"

    def _device_samplerate(self, device: Optional[int]) -> int:
        try:
            import sounddevice as sd
            info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
            rate = int(info.get("default_samplerate") or self.sample_rate)
            return rate if rate > 0 else self.sample_rate
        except Exception:
            return self.sample_rate

    def _add_transcript(self, transcript: AudioTranscript) -> None:
        self.transcripts.append(transcript)
        line = f"[{datetime.fromtimestamp(transcript.timestamp).isoformat(timespec='seconds')}] [{transcript.source}] {transcript.text}\n"
        try:
            with self.transcript_path.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


class MultiAudioListener:
    """Run several AudioListener instances at once for mixed PC/meeting audio."""

    PREFERRED_PRIORITY = (
        "stream",
        "stereomix",
        "stereo mix",
        "chat capture",
        "cable output",
        "what u hear",
        "was sie hoeren",
        "was sie hören",
    )
    EXCLUDE_KEYWORDS = (
        "microphone",
        "mikrofon",
        "droidcam",
        "soundmapper",
        "primärer",
        "primaerer",
    )

    def __init__(
        self,
        sandbox_dir: Path,
        model_name: str = "base",
        source_provider: Optional[Callable[[], str]] = None,
    ):
        self.sandbox_dir = Path(sandbox_dir)
        self.model_name = model_name
        self.source_provider = source_provider
        self.listeners: List[AudioListener] = []
        session_name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.session_dir = Path(sandbox_dir) / "audio" / "temp_sessions" / session_name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.session_dir / "transcript_all.txt"

    def pick_candidate_devices(self, max_devices: int = 2) -> Dict[str, Any]:
        probe = AudioListener(self.sandbox_dir, self.model_name)
        result = probe.list_devices()
        if not result.get("ok"):
            return result

        devices = result.get("devices", [])
        preferred = []
        for keyword in self.PREFERRED_PRIORITY:
            for dev in devices:
                name = dev.get("name", "").lower()
                if any(blocked in name for blocked in self.EXCLUDE_KEYWORDS):
                    continue
                if keyword in name and dev not in preferred:
                    preferred.append(dev)

        selected = preferred[:max_devices] if preferred else devices[:1]
        return {"ok": True, "devices": selected}

    def start(self, devices: Optional[List[int]] = None, live_print: bool = True) -> Dict[str, Any]:
        if self.is_running():
            return {"ok": True, "message": "Multi audio listener already running"}

        if devices is None:
            picked = self.pick_candidate_devices()
            if not picked.get("ok"):
                return picked
            devices = [dev["index"] for dev in picked.get("devices", [])]

        if not devices:
            return {"ok": False, "error": "No audio devices selected"}

        started = []
        errors = []
        for device in devices:
            listener = AudioListener(
                self.sandbox_dir,
                self.model_name,
                device=device,
                source_provider=self.source_provider,
            )
            listener.session_dir = self.session_dir
            listener.transcript_path = self.transcript_path
            open_check = listener.measure_level(device=device, seconds=0.25)
            if not open_check.get("ok"):
                errors.append({"device": device, "error": open_check})
                continue
            result = listener.start(device=device, live_print=live_print)
            if result.get("ok"):
                self.listeners.append(listener)
                started.append(device)
            else:
                errors.append({"device": device, "error": result})

        return {"ok": bool(started), "started": started, "errors": errors}

    def stop(self) -> Dict[str, Any]:
        total = 0
        for listener in self.listeners:
            result = listener.stop()
            total += int(result.get("transcripts", 0))
        return {"ok": True, "message": "Multi audio listener stopped", "transcripts": total}

    def is_running(self) -> bool:
        return any(listener.is_running for listener in self.listeners)

    def get_transcript_text(self, limit_chars: int = 10000) -> str:
        chunks: List[AudioTranscript] = []
        for listener in self.listeners:
            chunks.extend(listener.transcripts)
        chunks.sort(key=lambda item: item.timestamp)
        text = "\n".join(f"[{item.source}] {item.text}" for item in chunks if item.text.strip())
        return text[-limit_chars:] if len(text) > limit_chars else text

    def clear(self) -> None:
        self.listeners.clear()

    def cleanup_temp_files(self) -> None:
        for listener in self.listeners:
            listener.clear()
        try:
            if self.transcript_path.exists():
                self.transcript_path.write_text("", encoding="utf-8")
        except Exception:
            pass

    def session_path(self) -> str:
        return str(self.session_dir)


__all__ = ["AudioListener", "AudioTranscript", "MultiAudioListener"]
