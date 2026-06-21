# Developer Guidelines (AGENTS.md)

Welcome to the `mcp-grpc-transport-py` project. This file provides generic guidelines for AI agents and developers modifying this codebase.

## Project Structure & Guidelines Pointers

This project uses a hierarchical guidelines model. For specific files and packages, consult their local guidelines files:
*   For the library core source code under `src/`: See [src/mcp_grpc_transport/AGENTS.md](src/mcp_grpc_transport/AGENTS.md)
*   For writing and executing tests under `tests/`: See [tests/AGENTS.md](tests/AGENTS.md)
*   For adding or modifying example scripts under `examples/`: See [examples/AGENTS.md](examples/AGENTS.md)

---

## Package Management

*   **Tooling:** Use **`uv`** for managing dependencies and running commands. **Never use `pip` directly.**
*   **Running Commands:** Run commands using `uv run`. For example:
    *   To run tests: `uv run pytest`
    *   To run formatting: `uv run ruff format .` (if ruff is added)
*   **Adding Dependencies:** Use `uv add <package>` or `uv add --dev <package>`. Avoid manual edits to `pyproject.toml` unless strictly necessary.

## General Coding Standards

*   **Line Length:** Keep bullet points and lines reasonably short to prevent wrapping.
*   **Formatting:** Maintain clean code formatting. Use standard formatting utilities where appropriate.
*   **Documentation:** Ensure all code edits are properly documented with clear explanations. Add inline comments for any non-obvious design choices.
*   **Commit Policy:** Do not commit changes to the repository without explicit user approval.
