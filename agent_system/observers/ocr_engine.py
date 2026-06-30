"""
OCR Engine: Text extraction from images
"""
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import io
from pathlib import Path
import warnings


class OCREngine:
    """
    OCR Engine mit Support für mehrere Backends.
    
    Priorät:
    1. EasyOCR (best quality, requires GPU)
    2. Tesseract (good quality, requires binary install)
    3. Fallback (no-op)
    """

    def __init__(self, backend: str = "auto"):
        """
        Args:
            backend: "easyocr", "tesseract", "auto"
        """
        self.backend = backend
        self.engine = None
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialisiert OCR Backend."""
        if self.backend in {"easyocr", "auto"}:
            try:
                warnings.filterwarnings(
                    "ignore",
                    message=r".*pin_memory.*no accelerator.*",
                    category=UserWarning,
                )
                import easyocr
                self.engine = easyocr.Reader(["de", "en"], gpu=False, verbose=False)
                self.backend = "easyocr"
                print("✅ OCR: EasyOCR loaded")
                return
            except ImportError:
                if self.backend == "easyocr":
                    raise
                print("⚠️  EasyOCR not available")

        if self.backend in {"tesseract", "auto"}:
            try:
                import pytesseract
                self.engine = pytesseract
                self.backend = "tesseract"
                print("✅ OCR: Tesseract loaded")
                return
            except ImportError:
                if self.backend == "tesseract":
                    raise
                print("⚠️  Tesseract not available")

        # Fallback
        self.engine = None
        self.backend = "none"
        print("⚠️  OCR: No backend available")

    def extract_text(self, image: Image.Image, languages: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Extrahiert Text aus Bild.
        
        Returns:
            {
                "text": "erkannter Text",
                "confidence": 0.95,
                "regions": [...],
                "backend": "easyocr",
            }
        """
        if not self.engine:
            return {"text": "", "confidence": 0.0, "backend": "none"}

        try:
            if self.backend == "easyocr":
                return self._extract_easyocr(image, languages)
            elif self.backend == "tesseract":
                return self._extract_tesseract(image)
            else:
                return {"text": "", "confidence": 0.0}
        
        except Exception as e:
            return {"error": str(e), "text": "", "confidence": 0.0}

    def _extract_easyocr(self, image: Image.Image, languages: Optional[List[str]]) -> Dict[str, Any]:
        """Extrahiert mit EasyOCR."""
        # Convert to RGB if needed
        if image.mode == "RGBA":
            image = image.convert("RGB")

        # EasyOCR erwartet numpy array
        import numpy as np
        img_array = np.array(image)

        results = self.engine.readtext(img_array, detail=1)

        # Aggregate text
        full_text = "\n".join([item[1] for item in results])
        
        # Average confidence
        confidences = [item[2] for item in results]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Extract regions
        regions = [
            {
                "text": item[1],
                "confidence": item[2],
                "bbox": item[0],  # List of 4 corner points
            }
            for item in results
        ]

        return {
            "text": full_text,
            "confidence": avg_confidence,
            "regions": regions,
            "num_regions": len(regions),
            "backend": "easyocr",
        }

    def _extract_tesseract(self, image: Image.Image) -> Dict[str, Any]:
        """Extrahiert mit Tesseract."""
        try:
            text = self.engine.image_to_string(image, lang="deu+eng")
            
            # Tesseract gibt nur Text, keine Confidence
            return {
                "text": text,
                "confidence": 0.8,  # Estimate
                "backend": "tesseract",
            }
        
        except Exception as e:
            return {"error": str(e), "text": "", "confidence": 0.0}

    def extract_code_blocks(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Erkennt Code-Blöcke in Bild (z.B. IDE-Screenshots).
        
        Returns: List of code blocks mit Text und Positionen
        """
        result = self.extract_text(image)
        text = result.get("text", "")
        regions = result.get("regions", [])

        # Einfache Heuristik: Zeilen mit Indentation oder Klammern = Code
        code_regions = []
        
        for region in regions:
            text_chunk = region.get("text", "").strip()
            
            # Check if looks like code
            if any(c in text_chunk for c in {"(", ")", "{", "}", "[", "]", ":", ";", "=", "def", "class", "import", "return"}):
                code_regions.append(region)

        return code_regions

    def analyze_error_messages(self, image: Image.Image) -> Optional[Dict[str, str]]:
        """
        Versucht Fehler-Meldungen zu erkennen.
        
        Returns: z.B. {"error_type": "SyntaxError", "line": "...", "message": "..."}
        """
        result = self.extract_text(image)
        text = result.get("text", "").lower()

        # Check for common error patterns
        error_keywords = [
            "error", "exception", "traceback", "failed", "failed",
            "syntaxerror", "typeerror", "valueerror", "keyerror",
            "importerror", "modulenotfounderror",
        ]

        detected_error = None
        for kw in error_keywords:
            if kw in text:
                detected_error = kw
                break

        if not detected_error:
            return None

        # Extract surrounding context (next 300 chars)
        lines = result.get("text", "").split("\n")
        
        return {
            "error_detected": True,
            "error_type": detected_error,
            "full_text": result.get("text", "")[:500],
        }


__all__ = ["OCREngine"]
