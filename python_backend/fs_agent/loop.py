"""Loop detection for FS-agent runs.

When the model repeats the same tool call with the same arguments (or stalls on
the same failing edit), the runner injects a SYSTEM notice telling the model it
is looping and what to do instead - and eventually stops the run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

MAX_IDENTICAL_CALLS = 2
MAX_CONSECUTIVE_ERRORS = 3
MAX_LOOP_NOTICES = 3


@dataclass
class LoopDetector:
    max_identical_calls: int = MAX_IDENTICAL_CALLS
    max_consecutive_errors: int = MAX_CONSECUTIVE_ERRORS
    _fingerprints: dict[str, int] = field(default_factory=dict)
    _consecutive_errors: int = 0
    _notices_sent: int = 0

    def record(self, tool_name: str, arguments: dict) -> str | None:
        """Register a call; return a system notice when a loop is detected (throttled)."""
        payload = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True, ensure_ascii=True)
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        self._fingerprints[fingerprint] = self._fingerprints.get(fingerprint, 0) + 1
        count = self._fingerprints[fingerprint]
        if count <= self.max_identical_calls:
            return None
        self._notices_sent += 1
        if self._notices_sent > MAX_LOOP_NOTICES:
            # Already told the model repeatedly; stay silent until the round cap ends the run.
            return None
        return (
            f"⚠️ SYSTEM: loop detected - this is call #{count} of '{tool_name}' with identical arguments. "
            "Change your approach: read the file again, use different arguments, or finish with your best result."
        )

    def record_error(self) -> str | None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= self.max_consecutive_errors:
            self._consecutive_errors = 0
            return (
                "⚠️ SYSTEM: several tool calls failed in a row. Stop retrying the same way. "
                "Re-read the relevant file, simplify the step, or explain what is blocking you."
            )
        return None

    def record_success(self) -> None:
        self._consecutive_errors = 0
