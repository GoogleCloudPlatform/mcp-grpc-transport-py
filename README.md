# MCP gRPC Transport (Python)

A pluggable gRPC-based transport implementation for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) Python SDK V2.

This library replaces the default JSON-RPC-over-streams transport with a high-performance, stateless gRPC implementation.

> [!WARNING]
> This package is currently in **active development** and exposes an **experimental API**. The APIs and Protobuf schema are subject to change and breaking modifications may occur as the Model Context Protocol V2 specification and Python SDK mature.

## Dependencies

This package requires the following core dependencies:
*   **`mcp` (Model Context Protocol Python SDK):** Pinned to version `2.1.1`.
*   **`grpcio`:** Required for asynchronous gRPC client and server communications (`grpcio>=1.74.0`).
*   **`mcp-grpc-transport-proto`:** Generated Protobuf message and service contracts.

## Features

*   **Pydantic Integration:** Automatically integrates with the Python SDK V2 Pydantic models, converting snake_case attributes to generated Protobuf messages.
*   **Dual Server Support:** Works with both the high-level `MCPServer` (via decorators like `@mcp.tool()`) and the low-level `Server` API.
*   **Managed & Unmanaged Lifecycles:** Allows embedding the gRPC server inside your existing gRPC application (unmanaged mode) or running it standalone (managed mode).

---

## Quick Start

Setting up the gRPC transport involves defining your server using the SDK's high-level `MCPServer` and connecting to it via `GRPCClientDispatcher` plugged into the `ClientSession`.

*   **Server Setup:** See [examples/simple_tool/server.py](examples/simple_tool/server.py) for a complete standalone server example.
*   **Client Setup:** See [examples/simple_tool/client.py](examples/simple_tool/client.py) to see how the client session connects and calls tools.

> **No MCP initialize handshake.** This transport intentionally skips the MCP initialize / capability-negotiation step. Do **not** call `await session.initialize()` on a `ClientSession` bound to `GRPCClientDispatcher`; invoke tool/resource methods directly. Notifications (`session.send_notification`) are not supported either.

Refer to the [Examples](#examples) section below on how to run them.

---

## Examples

We provide runnable examples demonstrating different MCP capabilities:

*   **Simple Tool Example ([examples/simple_tool/](examples/simple_tool)):** Demonstrates how to register a basic calculator tool using the high-level `MCPServer` decorators and call it from a client session.
*   **Simple Resource Example ([examples/simple_resource/](examples/simple_resource)):** Demonstrates registering static and templated text resources on the server and listing/reading them from the client.

To run any example:
1. Start the server:
   ```bash
   uv run python examples/<example_name>/server.py
   ```
2. In a separate terminal, run the client:
   ```bash
   uv run python examples/<example_name>/client.py
   ```

---

## Documentation

*   For details on the client-side design, see [docs/client.md](docs/client.md).
*   For details on the server-side design, see [docs/server.md](docs/server.md).
*   For developer guidelines, see [AGENTS.md](AGENTS.md).

## Development

This repository uses `uv` for managing python environments, formatting, and running tests.

Tests use `absl.testing.absltest` (for sync) and `unittest.IsolatedAsyncioTestCase` (for async). No pytest.

### Run Tests
```bash
uv run python -m unittest discover -s tests -v
```

### Run Tests with Coverage Report
```bash
uv run coverage run --source=src/mcp_grpc_transport -m unittest discover -s tests
uv run coverage report -m
```
