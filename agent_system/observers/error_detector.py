"""
Error Detector: Real-time error detection in code/IDE
"""
import re
from typing import Dict, List, Optional, Any
from PIL import Image


class ErrorDetector:
    """
    Erkennt Code-Fehler automatisch.
    
    Features:
    - Syntax Error Detection (Regex)
    - Common Python/JS/Rust Patterns
    - IDE Error Highlights (Red underlines)
    - Performance Warnings
    """

    # Error patterns (Language Agnostic)
    ERROR_PATTERNS = {
        "undefined": re.compile(r"(undefined|not defined|not found|NameError)", re.I),
        "syntax": re.compile(r"(SyntaxError|Unexpected|Expected|Expected:|Invalid|Illegal)", re.I),
        "type": re.compile(r"(TypeError|type mismatch|Cannot|incompatible|wrong type)", re.I),
        "import": re.compile(r"(ImportError|ModuleNotFoundError|cannot import|No module)", re.I),
        "attribute": re.compile(r"(AttributeError|has no attribute|attribute error)", re.I),
        "index": re.compile(r"(IndexError|out of range|index out|Index Out)", re.I),
        "key": re.compile(r"(KeyError|key error|Unknown key)", re.I),
        "runtime": re.compile(r"(RuntimeError|Exception|Error:|failed|Fatal)", re.I),
    }

    # Common mistakes
    TYPOS = {
        r"\bpring\b": "print",
        r"\blen\b": "len (correct)",
        r"\bdefine\b": "def",
        r"\bif\s*\(": "if (use : not ())",
        r"\bforr\b": "for",
    }

    # Performance Warnings
    PERFORMANCE_ISSUES = {
        "N+1": re.compile(r"(for|while).*:(.*for.*:)", re.DOTALL),
        "deep_recursion": re.compile(r"def\s+\w+\([^)]*\):[^}]*\w+\(", re.I),  # Simplified
        "global_access": re.compile(r"\bglobal\s+\w+", re.I),
    }

    def __init__(self):
        pass

    def detect_errors_in_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Erkennt Fehler im Text.
        
        Returns: List von Fehlern mit Typ und Position
        """
        errors = []
        lines = text.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Check each error pattern
            for error_type, pattern in self.ERROR_PATTERNS.items():
                if pattern.search(line):
                    errors.append({
                        "type": error_type,
                        "line": line_num,
                        "text": line.strip(),
                        "severity": "high",
                    })

            # Check typos
            for typo_pattern, correction in self.TYPOS.items():
                if re.search(typo_pattern, line):
                    errors.append({
                        "type": "typo",
                        "line": line_num,
                        "text": line.strip(),
                        "suggestion": correction,
                        "severity": "medium",
                    })

        return errors

    def detect_in_code_screenshot(self, image: Image.Image, ocr_engine) -> Dict[str, Any]:
        """
        Erkennt Fehler in Code-Screenshot (mit OCR).
        """
        # Extract text mit OCR
        ocr_result = ocr_engine.extract_text(image)
        text = ocr_result.get("text", "")

        # Detect errors
        errors = self.detect_errors_in_text(text)

        # Also check for error highlights (red underlines, etc.)
        # This would require image analysis - simplified for now
        
        return {
            "errors_detected": len(errors) > 0,
            "num_errors": len(errors),
            "errors": errors,
            "ocr_confidence": ocr_result.get("confidence", 0.0),
        }

    def detect_in_ide_screenshot(self, image: Image.Image) -> Dict[str, Any]:
        """
        Erkennt IDE-Fehler-Indikatoren:
        - Rote Wellenlinie unter Fehler
        - Error-Panel unten
        - Line Numbers mit X
        """
        # Simple pixel-based detection
        # In production: Use more sophisticated image analysis
        
        pixels = image.load()
        width, height = image.size

        # Look for red pixels (common IDE error highlighting)
        red_pixels = 0
        for x in range(0, width, 10):  # Sample
            for y in range(0, height, 10):
                r, g, b = pixels[x, y][:3]
                if r > 150 and g < 100 and b < 100:
                    red_pixels += 1

        has_error_indicators = red_pixels > (width * height) / (10 * 10) * 0.05

        return {
            "has_error_indicators": has_error_indicators,
            "red_pixel_count": red_pixels,
            "recommendation": "Check IDE for errors" if has_error_indicators else "No obvious errors",
        }

    def suggest_fixes(self, errors: List[Dict[str, Any]]) -> List[str]:
        """
        Schlägt Fixes vor.
        """
        suggestions = []

        for error in errors:
            error_type = error.get("type", "")
            text = error.get("text", "")

            if error_type == "undefined":
                suggestions.append(f"Line {error['line']}: Check variable name or import it")
            elif error_type == "syntax":
                suggestions.append(f"Line {error['line']}: Check syntax (missing : or bracket?)")
            elif error_type == "typo":
                suggestions.append(f"Line {error['line']}: Did you mean '{error.get('suggestion', 'this')}'?")
            elif error_type == "import":
                suggestions.append(f"Line {error['line']}: Install missing module or check import path")
            else:
                suggestions.append(f"Line {error['line']}: {error_type.upper()} - Review this line")

        return suggestions


__all__ = ["ErrorDetector"]
