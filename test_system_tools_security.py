from pathlib import Path
from tempfile import TemporaryDirectory

from agent_system.tools.system import SystemTools


class _Sandbox:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def is_within(self, base: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(base)
            return True
        except ValueError:
            return False


def _tools(tmp: str) -> SystemTools:
    return SystemTools(_Sandbox(Path(tmp).resolve()))


def test_git_status_short_is_allowed():
    with TemporaryDirectory() as tmp:
        ok, reason = _tools(tmp)._validate_command("git", ["status", "--short"])
        assert ok, reason


def test_git_no_index_is_blocked_even_for_diff():
    with TemporaryDirectory() as tmp:
        ok, reason = _tools(tmp)._validate_command("git", ["diff", "--no-index", "--", "a.txt", "C:\\Windows\\win.ini"])
        assert ok is False
        assert "--no-index" in reason


def test_git_absolute_and_parent_paths_are_blocked():
    with TemporaryDirectory() as tmp:
        tools = _tools(tmp)
        ok_abs, reason_abs = tools._validate_command("git", ["diff", "--", "C:\\Windows\\win.ini"])
        ok_parent, reason_parent = tools._validate_command("git", ["diff", "--", "..\\secret.txt"])
        assert ok_abs is False
        assert "relative sandbox paths" in reason_abs
        assert ok_parent is False
        assert "relative sandbox paths" in reason_parent


def test_git_pull_is_not_allowed():
    with TemporaryDirectory() as tmp:
        ok, reason = _tools(tmp)._validate_command("git", ["pull"])
        assert ok is False
        assert "not allowed" in reason


if __name__ == "__main__":
    test_git_status_short_is_allowed()
    test_git_no_index_is_blocked_even_for_diff()
    test_git_absolute_and_parent_paths_are_blocked()
    test_git_pull_is_not_allowed()
    print("system tools security tests passed")
