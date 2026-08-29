"""Filesystem tools for the FS agent: project scaffolding, edits with old_string
verification, AGENTS.md rules per folder, and fallow-powered code inspection.

Every tool receives the jail and raises JailError / ToolFailure instead of ever
touching a path outside the projects root.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .jail import JailError, PathJail

MAX_FILE_BYTES = 256_000
MAX_READ_CHARS = 20_000
MAX_TREE_ENTRIES = 200
MAX_NEW_FILES = 120


class ToolFailure(Exception):
    """A tool-level failure that is fed back to the model as correction feedback."""


AGENTS_MD_TEMPLATE = """# AGENTS.md — rules for AI agents in this folder

You are an autonomous coding agent working inside **{folder}**. Follow the
[agents.md](https://agents.md) open standard: this file is your contract.

## Absolute boundaries
1. Never modify, create or delete anything outside the current project folder.
2. Never overwrite a file blindly. For edits you MUST pass the exact
   `old_string` from the current file content; if it does not match, STOP,
   re-read the file with `read_file`, and retry with the corrected string.
3. Never invent file contents. Always read before editing an existing file.
4. Create every file COMPLETE — no placeholders, no "TODO: implement".
5. Keep every file syntactically valid after each edit.

## Working rules
- Maintain the todo list: mark steps `completed` as soon as they are really done.
- Prefer small, focused files with clear names; group into subfolders by role.
- Every subfolder you create gets its own AGENTS.md (copy this structure).
- After structural changes, run `fallow inspect --file <path>` to verify.

## This folder
{purpose}
"""

README_TEMPLATE = """# {name}

{description}

Created by the Local Agent Studio filesystem agent team on {date}.

## Layout
- This root README explains what the project is.
- `docs/original_request.md` holds the verbatim user request every agent must honor.
- Each subfolder carries its own `AGENTS.md` with binding rules for agents.
"""


def _reject_none(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(f"Argument '{field}' must be a non-empty string.")


class FsTools:
    """All jailed filesystem capabilities exposed to the FS agent team."""

    def __init__(self, jail: PathJail) -> None:
        self.jail = jail

    # -- introspection ----------------------------------------------------

    def tree(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = arguments.get("path", ".")
        entries = self.jail.tree(str(path), max_entries=MAX_TREE_ENTRIES)
        return {"ok": True, "root": self.jail.root.name, "entries": entries}

    def read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _reject_none(arguments.get("path"), "path")
        try:
            path = self.jail.resolve(str(arguments["path"]), must_exist=True)
        except JailError as exc:
            raise ToolFailure(str(exc)) from exc
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise ToolFailure(f"File too large to read ({len(data)} bytes).")
        text = data.decode("utf-8", errors="replace")[:MAX_READ_CHARS]
        truncated = len(data) > MAX_READ_CHARS
        return {
            "ok": True,
            "path": self.jail.relative_to_root(path),
            "content": text,
            "truncated": truncated,
            "total_chars": len(data.decode("utf-8", errors="replace")),
        }

    # -- project scaffolding ----------------------------------------------

    def create_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _reject_none(arguments.get("name"), "name")
        _reject_none(arguments.get("description"), "description")
        name = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(arguments["name"]).strip()).strip("-.")
        if not name or name in {".", ".."}:
            raise ToolFailure("Project name produced an invalid folder name.")
        description = str(arguments["description"]).strip()
        original_request = str(arguments.get("original_request", description)).strip()

        project = self.jail.resolve(name)
        if project.exists():
            raise ToolFailure(f"Project folder already exists: {name}. Work inside it instead.")
        docs = project / "docs"
        docs.mkdir(parents=True)
        date = __import__("datetime").date.today().isoformat()

        base_dir = self.jail.root.resolve()
        
        readme_path = (project / "README.md").resolve()
        try:
            readme_path.relative_to(base_dir)
        except ValueError:
            raise ToolFailure("Invalid file path")
        readme_path.write_text(
            README_TEMPLATE.format(name=name, description=description, date=date), encoding="utf-8"
        )
        
        agents_md_path = (project / "AGENTS.md").resolve()
        try:
            agents_md_path.relative_to(base_dir)
        except ValueError:
            raise ToolFailure("Invalid file path")
        agents_md_path.write_text(
            AGENTS_MD_TEMPLATE.format(folder=name, purpose="Project root - own the overall structure and finish state."),
            encoding="utf-8",
        )
        
        original_request_path = (docs / "original_request.md").resolve()
        try:
            original_request_path.relative_to(base_dir)
        except ValueError:
            raise ToolFailure("Invalid file path")
        original_request_path.write_text(
            f"# Original user request (verbatim, every agent must honor this)\n\n{original_request}\n",
            encoding="utf-8",
        )
        
        decisions_path = (docs / "decisions.md").resolve()
        try:
            decisions_path.relative_to(base_dir)
        except ValueError:
            raise ToolFailure("Invalid file path")
        decisions_path.write_text(
            "# Decision log\n\nEvery agent appends its structural decisions here (one bullet per decision, newest first).\n",
            encoding="utf-8",
        )
        return {
            "ok": True,
            "project": name,
            "created": ["README.md", "AGENTS.md", "docs/original_request.md", "docs/decisions.md"],
            "note": "Create further subfolders with create_folder; each gets its own AGENTS.md automatically.",
        }

    def create_folder(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _reject_none(arguments.get("path"), "path")
        purpose = str(arguments.get("purpose", "Working folder for agents.")).strip()
        try:
            folder = self.jail.resolve(str(arguments["path"]))
        except JailError as exc:
            raise ToolFailure(str(exc)) from exc
        if folder.exists():
            raise ToolFailure(f"Folder already exists: {arguments['path']}")
        if folder.parent != self.jail.root and not folder.parent.exists():
            raise ToolFailure(f"Parent folder does not exist yet: {arguments['path']}")
        if folder.parent == self.jail.root:
            raise ToolFailure("Create folders inside a project, not directly at the jail root.")
        folder.mkdir(parents=True)
        agents_md_path = (folder / "AGENTS.md").resolve()
        base_dir = self.jail.root.resolve()
        try:
            agents_md_path.relative_to(base_dir)
        except ValueError:
            raise ToolFailure("Invalid file path")
        agents_md_path.write_text(
            AGENTS_MD_TEMPLATE.format(folder=folder.name, purpose=purpose), encoding="utf-8"
        )
        return {"ok": True, "folder": self.jail.relative_to_root(folder), "agents_md": True}

    # -- writing / editing --------------------------------------------------

    def write_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _reject_none(arguments.get("path"), "path")
        _reject_none(arguments.get("content"), "content")
        content = str(arguments["content"])
        if "TODO: implement" in content or "ADD LOGIC HERE" in content.upper():
            raise ToolFailure("Rejected: the file contains placeholder markers. Write complete code or instructions.")
        try:
            path = self.jail.resolve(str(arguments["path"]))
            self.jail.ensure_parent(path)
        except JailError as exc:
            raise ToolFailure(str(exc)) from exc
        overwrite = bool(arguments.get("overwrite", False))
        if path.exists() and not overwrite:
            raise ToolFailure(f"File already exists: {arguments['path']}. Read it and use edit_file instead of overwriting.")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ToolFailure("File content exceeds the 256 KB limit.")
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": self.jail.relative_to_root(path), "bytes": len(content.encode("utf-8"))}

    def edit_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _reject_none(arguments.get("path"), "path")
        _reject_none(arguments.get("old_string"), "old_string")
        _reject_none(arguments.get("new_string"), "new_string")
        try:
            path = self.jail.resolve(str(arguments["path"]), must_exist=True)
        except JailError as exc:
            raise ToolFailure(str(exc)) from exc
        current = path.read_text(encoding="utf-8", errors="strict")
        old_string = str(arguments["old_string"])
        new_string = str(arguments["new_string"])
        occurrences = current.count(old_string)
        if occurrences == 0:
            raise ToolFailure(
                "MISMATCH: old_string was not found in the file. The file may have changed or your copy was "
                "inaccurate. Re-read the file with read_file now, then retry the edit with the exact text."
            )
        allow_multiple = bool(arguments.get("allow_multiple", False))
        if occurrences > 1 and not allow_multiple:
            raise ToolFailure(
                f"AMBIGUOUS: old_string occurs {occurrences} times. Pass a longer, unique old_string "
                "(with surrounding lines) or set allow_multiple=true."
            )
        updated = current.replace(old_string, new_string) if allow_multiple else current.replace(old_string, new_string, 1)
        base_dir = self.jail.root.resolve()
        target_path = path.resolve()
        try:
            target_path.relative_to(base_dir)
        except ValueError:
            raise ToolFailure("Invalid file path")
        path.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": self.jail.relative_to_root(path), "replacements": occurrences if allow_multiple else 1}

    # -- analysis -----------------------------------------------------------

    def fallow_analyze(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run the fallow codebase analyzer inside the project (jailed)."""
        import asyncio
        import shutil

        if shutil.which("fallow") is None and shutil.which("bunx") is None and shutil.which("npx") is None:
            return {"ok": False, "error": "fallow is not installed in this environment; analysis skipped."}
        project_rel = str(arguments.get("project", ""))
        _reject_none(project_rel, "project")
        subcommand = str(arguments.get("subcommand", "audit"))
        allowed = {"audit", "health", "dead-code", "dupes", "inspect"}
        if subcommand not in allowed:
            raise ToolFailure(f"Unknown fallow subcommand '{subcommand}'. Allowed: {sorted(allowed)}")
        try:
            command, _workspace = self.jail.sandboxed_command(project_rel, ["fallow", subcommand])
        except JailError as exc:
            raise ToolFailure(str(exc)) from exc

        if not self.jail.docker_available():
            # No Docker in this environment: run fallow read-only against the jailed folder.
            host_command = ["fallow" if shutil.which("fallow") else "bunx", "fallow", subcommand]
            if shutil.which("fallow") is None:
                host_command = ["bunx", "fallow", subcommand]
            extra = arguments.get("args")
            if isinstance(extra, list):
                host_command += [str(item) for item in extra][:8]
            try:
                result = subprocess_run(host_command, cwd=str(self.jail.resolve(project_rel)))
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                return {"ok": False, "error": f"fallow failed: {exc}"}
            return {"ok": result.returncode == 0, "exit_code": result.returncode, "output": result.stdout[-6000:]}

        try:
            result = asyncio.get_event_loop().run_until_complete(asyncio.to_thread(_docker_run, command, timeout=self.jail.docker.timeout_seconds))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Docker sandbox run failed: {exc}"}
        return {"ok": result.returncode == 0, "exit_code": result.returncode, "output": (result.stdout + result.stderr)[-6000:]}


def _docker_run(command: list[str], timeout: int):
    import subprocess

    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def subprocess_run(command: list[str], cwd: str):
    import subprocess

    return subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=cwd)


def build_tool_registry(jail: PathJail):
    """Return the plain skill descriptors for the FS agent (name, schema, executor)."""
    tools = FsTools(jail)

    def executor(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "fs_tree": tools.tree,
            "fs_read_file": tools.read_file,
            "fs_create_project": tools.create_project,
            "fs_create_folder": tools.create_folder,
            "fs_write_file": tools.write_file,
            "fs_edit_file": tools.edit_file,
            "fallow_analyze": tools.fallow_analyze,
        }
        fn = mapping.get(name)
        if fn is None:
            raise ToolFailure(f"Unknown filesystem tool '{name}'.")
        return fn(arguments)

    schemas = [
        {
            "name": "fs_tree",
            "description": "List files and folders inside the jailed projects workspace (use before editing to orient yourself).",
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Folder relative to projects/, default '.'"}}, "additionalProperties": False},
        },
        {
            "name": "fs_read_file",
            "description": "Read a file inside projects/. ALWAYS read before editing; required after any MISMATCH error.",
            "parameters": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}, "additionalProperties": False},
        },
        {
            "name": "fs_create_project",
            "description": "Scaffold projects/<name>/ with README.md, AGENTS.md, docs/original_request.md (verbatim user request) and docs/decisions.md.",
            "parameters": {
                "type": "object",
                "required": ["name", "description"],
                "properties": {
                    "name": {"type": "string", "description": "Project/folder name (sanitized)"},
                    "description": {"type": "string", "description": "What the project is"},
                    "original_request": {"type": "string", "description": "The verbatim user request stored for every agent to read"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "fs_create_folder",
            "description": "Create a subfolder inside a project; an AGENTS.md with your rules/purpose is generated automatically.",
            "parameters": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "purpose": {"type": "string"}}, "additionalProperties": False},
        },
        {
            "name": "fs_write_file",
            "description": "Create a NEW file with complete content (placeholders rejected; overwrite=false on existing files).",
            "parameters": {"type": "object", "required": ["path", "content"], "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "overwrite": {"type": "boolean"}}, "additionalProperties": False},
        },
        {
            "name": "fs_edit_file",
            "description": "Edit an existing file by exact old_string match. On MISMATCH you MUST fs_read_file and retry with corrected text.",
            "parameters": {
                "type": "object",
                "required": ["path", "old_string", "new_string"],
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "allow_multiple": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "fallow_analyze",
            "description": "Run the fallow static analyzer (audit/health/dead-code/dupes/inspect) on a project inside the sandbox.",
            "parameters": {"type": "object", "required": ["project"], "properties": {"project": {"type": "string"}, "subcommand": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": False},
        },
    ]
    return schemas, executor
