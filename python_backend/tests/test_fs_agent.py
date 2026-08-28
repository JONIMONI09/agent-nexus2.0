from __future__ import annotations

import asyncio
import json

import pytest

from python_backend.fs_agent.fs_tools import FsTools, ToolFailure
from python_backend.fs_agent.jail import JailError, PathJail
from python_backend.fs_agent.loop import LoopDetector
from python_backend.fs_agent.todos import TodoBoard


@pytest.fixture()
def jail(tmp_path):
    return PathJail(root=tmp_path / "projects")


@pytest.fixture()
def tools(jail):
    return FsTools(jail)


# --- jail security ---------------------------------------------------------

def test_jail_blocks_traversal(jail) -> None:
    with pytest.raises(JailError):
        jail.resolve("../../etc/passwd")
    with pytest.raises(JailError):
        jail.resolve("/etc/passwd")
    with pytest.raises(JailError):
        jail.resolve("project/../../../outside")


def test_jail_allows_nested_paths(jail) -> None:
    target = jail.resolve("my-app/src/main.py")
    assert str(target).startswith(str(jail.root))


def test_sandboxed_command_uses_hardened_flags(jail) -> None:
    folder = jail.resolve("demo")
    folder.mkdir()
    argv, workspace = jail.sandboxed_command("demo", ["python", "-c", "print('x')"])
    joined = " ".join(argv)
    for flag in ("--network none", "--cap-drop ALL", "no-new-privileges", "--read-only", "65532:65532", "--pids-limit"):
        assert flag in joined, f"missing hardening flag: {flag}"
    assert str(workspace) == str(folder)


# --- project scaffolding ----------------------------------------------------

def test_create_project_builds_full_structure(tools) -> None:
    result = tools.create_project({
        "name": "My App!",
        "description": "A demo",
        "original_request": "Build me a demo app with tests",
    })
    assert result["ok"] is True
    sanitized = result["project"]  # e.g. "My-App"
    tree = tools.tree({"path": sanitized})
    joined = "\n".join(tree["entries"])
    for expected in ("README.md", "AGENTS.md", "docs/original_request.md", "docs/decisions.md"):
        assert expected in joined
    request = tools.read_file({"path": f"{sanitized}/docs/original_request.md"})
    assert "Build me a demo app with tests" in request["content"]


def test_create_folder_writes_agents_md(tools) -> None:
    tools.create_project({"name": "proj", "description": "d"})
    result = tools.create_folder({"path": "proj/src", "purpose": "Source files"})
    assert result["agents_md"] is True
    agents = tools.read_file({"path": "proj/src/AGENTS.md"})
    assert "Source files" in agents["content"]
    assert "agents.md" in agents["content"].lower()


def test_create_folder_rejects_jail_root_level(tools) -> None:
    with pytest.raises(ToolFailure):
        tools.create_folder({"path": "loose-folder"})


# --- write/edit verification ------------------------------------------------

def test_write_rejects_placeholders_and_overwrite(tools) -> None:
    with pytest.raises(ToolFailure):
        tools.write_file({"path": "p/a.py", "content": "def run():\n    # TODO: implement\n"})
    tools.create_project({"name": "proj2", "description": "d"})
    tools.write_file({"path": "proj2/app.py", "content": "print(1)"})
    with pytest.raises(ToolFailure):
        tools.write_file({"path": "proj2/app.py", "content": "print(2)"})


def test_edit_mismatch_forces_reread_protocol(tools) -> None:
    tools.create_project({"name": "proj3", "description": "d"})
    tools.write_file({"path": "proj3/app.py", "content": "value = 1\n"})
    with pytest.raises(ToolFailure) as excinfo:
        tools.edit_file({"path": "proj3/app.py", "old_string": "value = 999", "new_string": "value = 2"})
    assert "MISMATCH" in str(excinfo.value) and "read_file" in str(excinfo.value)
    # After re-reading, the corrected old_string works.
    fresh = tools.read_file({"path": "proj3/app.py"})
    result = tools.edit_file({"path": "proj3/app.py", "old_string": "value = 1", "new_string": "value = 2"})
    assert result["ok"] is True
    assert "value = 2" in tools.read_file({"path": "proj3/app.py"})["content"]
    assert fresh["content"]


def test_edit_ambiguous_requires_longer_string(tools) -> None:
    tools.create_project({"name": "proj4", "description": "d"})
    tools.write_file({"path": "proj4/app.py", "content": "x = 'a'\ny = 'a'\n"})
    with pytest.raises(ToolFailure) as excinfo:
        tools.edit_file({"path": "proj4/app.py", "old_string": "= 'a'", "new_string": "= 'b'"})
    assert "AMBIGUOUS" in str(excinfo.value)
    result = tools.edit_file({"path": "proj4/app.py", "old_string": "y = 'a'", "new_string": "y = 'b'"})
    assert result["ok"] is True


# --- todos -------------------------------------------------------------------

def test_todoboard_tracks_and_blocks() -> None:
    board = TodoBoard()
    board.set_all(["scaffold project", "write core", "write tests"])
    assert len(board.open_items()) == 3
    assert board.complete("todo-2") is True
    assert board.complete("todo-99") is False
    assert [todo.task for todo in board.open_items()] == ["scaffold project", "write tests"]
    assert board.summary() == "1/3 todos completed"


def test_complexity_detection() -> None:
    board = TodoBoard()
    assert board.looks_complex("Build a full project with a server and tests for each module") is True
    assert board.looks_complex("fix typo") is False


# --- loop detector -----------------------------------------------------------

def test_loop_detector_fires_system_notice() -> None:
    guard = LoopDetector()
    args = {"path": "x", "old_string": "a", "new_string": "b"}
    assert guard.record("fs_edit_file", args) is None
    assert guard.record("fs_edit_file", args) is None
    notice = guard.record("fs_edit_file", args)
    assert notice and "loop detected" in notice and "SYSTEM" in notice


def test_loop_detector_error_streak() -> None:
    guard = LoopDetector()
    assert guard.record_error() is None
    assert guard.record_error() is None
    notice = guard.record_error()
    assert notice and "failed in a row" in notice
    guard.record_success()
    assert guard.record_error() is None
