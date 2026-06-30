"""
Ollama Native Tool-Calling (NO REGEX PARSING!)
Nutzt das echte Ollama tools-Protokoll für strukturierte Funktion-Aufrufe.
"""
import json
import requests
from typing import Any, Dict, List, Optional, Callable, Tuple
import time

class OllamaNative:
    """
    Kommuniziert mit Ollama über das native tools-Protokoll.
    
    Beispiel-Response (strukturiert):
    {
        "model": "qwen2.5:7b-instruct",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "wb_write_file",
                        "arguments": {"filename": "test.py", "content": "..."}
                    }
                }
            ]
        }
    }
    """

    def __init__(
        self,
        model: str = "qwen3-coder:30b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 120,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.chat_url = f"{self.base_url}/api/chat"
        self.enable_tools = True

    def set_model(self, model: str) -> None:
        """Switch active Ollama model for the next request."""
        if model:
            self.model = model

    def set_tools_enabled(self, enabled: bool) -> None:
        """Enable/disable sending Ollama tools for models without tool support."""
        self.enable_tools = enabled

    def register_tools(self, tool_funcs: Dict[str, Callable]) -> "OllamaNative":
        """
        Registriert verfügbare Tools für den Ollama-Chat.
        
        tool_funcs: {
            "wb_write_file": <function>,
            "wb_read_file": <function>,
            ...
        }
        """
        self.tool_funcs = tool_funcs
        self._build_tool_definitions()
        return self

    def _build_tool_definitions(self) -> None:
        """Baut Tool-Definitionen für Ollama."""
        self.tool_defs = []
        for name, func in self.tool_funcs.items():
            # Einfache Heuristik: Docstring parsen oder aus Signatur
            doc = (func.__doc__ or "").split("\n")[0]
            sig = self._get_func_signature(func)
            
            self.tool_defs.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": doc or f"Tool: {name}",
                    "parameters": {
                        "type": "object",
                        "properties": sig["properties"],
                        "required": sig.get("required", []),
                    }
                }
            })

    def _get_func_signature(self, func: Callable) -> Dict[str, Any]:
        """
        Extrakt Parameter aus Funktion (vereinfacht).
        Für produktive Version: inspect.signature verwenden.
        """
        import inspect
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in {"self", "cls"}:
                continue

            # Typ erraten
            type_hint = param.annotation
            if type_hint == inspect.Parameter.empty:
                type_str = "string"
            elif type_hint == int:
                type_str = "integer"
            elif type_hint == bool:
                type_str = "boolean"
            elif type_hint == list:
                type_str = "array"
            elif type_hint == dict:
                type_str = "object"
            else:
                type_str = "string"

            properties[param_name] = {"type": type_str}
            
            # Kein Default = erforderlich
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {"properties": properties, "required": required}

    def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_retries: int = 3,
        options: Optional[Dict[str, Any]] = None,
        format_schema: Optional[Dict[str, Any]] = None,
        response_format: Optional[Any] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Chat mit Ollama mit natives Tool-Calling.
        
        Returns:
            (response_text, tool_call_dict or None)
            
        tool_call_dict: {"name": "tool_name", "arguments": {...}}
        """
        if system:
            messages = [{"role": "system", "content": system}] + messages

        for attempt in range(max_retries):
            try:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                }
                if options:
                    payload["options"] = options
                if format_schema is not None:
                    payload["format"] = format_schema
                elif response_format is not None:
                    payload["format"] = response_format
                
                # Nur Tools senden, wenn registriert
                if self.enable_tools and hasattr(self, "tool_defs") and self.tool_defs:
                    payload["tools"] = self.tool_defs

                r = requests.post(
                    self.chat_url,
                    json=payload,
                    timeout=self.timeout,
                )
                try:
                    r.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    detail = r.text[:1000] if r.text else str(e)
                    raise RuntimeError(f"{e}; response={detail}") from e
                data = r.json()

                msg = data.get("message", {}) or {}
                content = msg.get("content", "").strip()
                
                # Tool-Call vorhanden?
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    tool_call = tool_calls[0]  # First call
                    func_info = tool_call.get("function", {})
                    return content, {
                        "name": func_info.get("name"),
                        "arguments": func_info.get("arguments", {}),
                    }

                return content, None

            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Ollama error after {max_retries} retries: {e}")
                time.sleep(2 ** attempt)

        return "", None

    def execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führt einen Tool-Call aus.
        
        Args:
            tool_call: {"name": "...", "arguments": {...}}
            
        Returns:
            {"ok": bool, ...}
        """
        tool_name = tool_call.get("name")
        args = tool_call.get("arguments", {})

        if not tool_name or tool_name not in self.tool_funcs:
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}

        try:
            result = self.tool_funcs[tool_name](**args)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check(self) -> Tuple[bool, str]:
        """Prüft, ob Ollama erreichbar ist."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            models = [m.get("name") for m in data.get("models", [])]
            if self.model in models:
                return True, f"OK: {self.model} available"
            return False, f"Model {self.model} not found. Available: {models}"
        except Exception as e:
            return False, f"Cannot reach Ollama: {e}"

    def list_models(self) -> List[str]:
        """Return installed Ollama model names."""
        r = requests.get(f"{self.base_url}/api/tags", timeout=5)
        r.raise_for_status()
        data = r.json()
        return [m.get("name") for m in data.get("models", [])]

    def choose_available_model(self, candidates: List[str]) -> Tuple[Optional[str], List[str]]:
        """Pick the first installed model from candidates."""
        installed = self.list_models()
        installed_set = set(installed)
        for candidate in candidates:
            if candidate in installed_set:
                return candidate, installed
        return None, installed
