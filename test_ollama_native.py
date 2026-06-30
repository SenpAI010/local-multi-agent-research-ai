from types import SimpleNamespace

from agent_system.core.ollama_native import OllamaNative


def test_multiple_tool_calls_are_rejected_explicitly():
    client = OllamaNative()

    class FakeRequests:
        @staticmethod
        def post(*_args, **_kwargs):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "a", "arguments": {}}},
                            {"function": {"name": "b", "arguments": {}}},
                        ],
                    }
                },
            )

    import agent_system.core.ollama_native as mod

    old_requests = mod.requests
    try:
        mod.requests = FakeRequests
        _content, tool_call = client.chat_with_tools([{"role": "user", "content": "x"}])
    finally:
        mod.requests = old_requests

    assert tool_call["name"] == "__error__"
    assert tool_call["arguments"]["error"] == "multiple_tool_calls_not_supported"


if __name__ == "__main__":
    test_multiple_tool_calls_are_rejected_explicitly()
    print("ollama native tests passed")

