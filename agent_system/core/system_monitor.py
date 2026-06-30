"""
Local resource monitor for adaptive model routing.
"""
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResourceSnapshot:
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    gpu_percent: Optional[float] = None
    vram_percent: Optional[float] = None

    @property
    def pressure(self) -> str:
        values = [v for v in (self.cpu_percent, self.ram_percent, self.gpu_percent, self.vram_percent) if v is not None]
        peak = max(values) if values else 0.0
        if peak >= 90:
            return "high"
        if peak >= 75:
            return "medium"
        return "low"


class SystemMonitor:
    """Best-effort local CPU/RAM/GPU monitor."""

    def snapshot(self) -> ResourceSnapshot:
        snap = ResourceSnapshot()
        try:
            import psutil
            snap.cpu_percent = float(psutil.cpu_percent(interval=0.05))
            snap.ram_percent = float(psutil.virtual_memory().percent)
        except Exception:
            win = self._windows_cpu_ram_snapshot()
            if win:
                snap.cpu_percent = win.get("cpu")
                snap.ram_percent = win.get("ram")

        gpu = self._nvidia_snapshot()
        if gpu:
            snap.gpu_percent = gpu.get("gpu")
            snap.vram_percent = gpu.get("vram")
        return snap

    def _nvidia_snapshot(self) -> Optional[dict]:
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                shell=False,
            )
        except Exception:
            return None

        if proc.returncode != 0 or not proc.stdout.strip():
            return None

        try:
            line = proc.stdout.strip().splitlines()[0]
            gpu_s, used_s, total_s = [part.strip() for part in line.split(",")]
            used = float(used_s)
            total = float(total_s)
            return {
                "gpu": float(gpu_s),
                "vram": (used / total * 100.0) if total else None,
            }
        except Exception:
            return None

    def _windows_cpu_ram_snapshot(self) -> Optional[dict]:
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
                    "$os=Get-CimInstance Win32_OperatingSystem; "
                    "$ram=(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize*100); "
                    "Write-Output \"$cpu,$ram\"",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                shell=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            cpu_s, ram_s = proc.stdout.strip().split(",", 1)
            return {"cpu": float(cpu_s), "ram": float(ram_s)}
        except Exception:
            return None

__all__ = ["SystemMonitor", "ResourceSnapshot"]
