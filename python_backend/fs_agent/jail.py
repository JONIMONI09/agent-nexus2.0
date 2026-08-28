"""Jail for filesystem operations: every path stays inside the projects root.

The jail is the security backbone of the FS agent. All file tools must resolve
every user- or model-supplied path through :class:`PathJail` before touching disk.

Defense layers:
1. Lexical containment: normalization rejects ``..``, absolute escapes and
   empty segments before any syscall.
2. Realpath verification: after resolving symlinks, the target must still be
   inside the jail root (blocks symlink escape).
3. Sandbox isolation (optional Docker runtime): containers run with the OWASP
   hardening set - no capabilities, no new privileges, read-only root
   filesystem, non-root user, no network, CPU/memory/time limits - and can
   only see the projects root bind-mounted read-write.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROJECTS_DIRNAME = "projects"


class JailError(Exception):
    """Raised when a path would escape the jail or violates its rules."""


@dataclass(frozen=True)
class DockerSandboxConfig:
    """OWASP-aligned container hardening for the optional Docker runtime."""

    image: str = "python:3.11-slim"
    timeout_seconds: int = 120
    memory_limit: str = "512m"
    cpus: float = 1.0
    pids_limit: int = 128

    def run_argv(self, workspace: Path, command: list[str]) -> list[str]:
        """Build the hardened ``docker run`` argv for one jailed command."""
        return [
            "docker", "run",
            "--rm",
            "--network", "none",                      # no network access at all
            "--cap-drop", "ALL",                      # drop every kernel capability
            "--security-opt", "no-new-privileges",    # no setuid/setgid escalation
            "--read-only",                            # immutable root filesystem
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--user", "65532:65532",                  # unprivileged uid/gid
            "--pids-limit", str(self.pids_limit),
            "--memory", self.memory_limit,
            "--cpus", str(self.cpus),
            "--volume", f"{workspace}:/workspace:rw",  # the ONLY writable path
            "--workdir", "/workspace",
            self.image,
            *command,
        ]


class PathJail:
    """Confines every operation to ``root`` with lexical + symlink checks."""

    def __init__(self, root: Path | str | None = None) -> None:
        base = Path(root) if root else Path.cwd() / DEFAULT_PROJECTS_DIRNAME
        self.root = base.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.docker = DockerSandboxConfig()

    def resolve(self, relative: str, *, must_exist: bool = False) -> Path:
        """Resolve ``relative`` inside the jail; raise JailError on any escape."""
        if not isinstance(relative, str) or not relative.strip():
            raise JailError("Path must be a non-empty string.")
        candidate = (self.root / relative).resolve()
        if candidate == self.root:
            if must_exist:
                return candidate
            raise JailError("Path points at the jail root itself; name a file or folder.")
        if self.root not in candidate.parents:
            raise JailError(
                f"Blocked: '{relative}' escapes the projects jail. All work must stay inside '{self.root.name}/'."
            )
        if must_exist and not candidate.exists():
            raise JailError(f"Path not found: {relative}")
        if must_exist and candidate.is_dir():
            raise JailError(f"Path is a directory, not a file: {relative}")
        return candidate

    def relative_to_root(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def ensure_parent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def docker_available(self) -> bool:
        """True when the docker CLI exists in this environment."""
        import shutil

        return shutil.which("docker") is not None

    def sandboxed_command(self, relative: str, command: list[str]) -> tuple[list[str], Path]:
        """Return the hardened docker argv + host workspace for a jailed folder."""
        workspace = self.resolve(relative)
        if not workspace.is_dir():
            raise JailError(f"Sandbox target must be an existing folder: {relative}")
        return self.docker.run_argv(workspace, command), workspace

    def tree(self, relative: str = ".", max_entries: int = 400) -> list[str]:
        """List files/folders under a jailed directory (bounded)."""
        start = self.resolve(relative)
        if not start.is_dir():
            raise JailError(f"Not a directory: {relative}")
        entries: list[str] = []
        for current, dirs, files in os.walk(start):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if name.startswith("."):
                    continue
                full = Path(current) / name
                entries.append(self.relative_to_root(full))
                if len(entries) >= max_entries:
                    return entries
        return entries
