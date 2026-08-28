# AGENTS.md — rules for AI agents in this folder

You are an autonomous coding agent working inside **demo-app**. Follow the
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
Project root - own the overall structure and finish state.
