# Core Library Guidelines (src/mcp_grpc_transport/AGENTS.md)

Guidelines for editing the core transport library package.

## Architecture Context
For an overview of the server and client implementation details, read the documentation files:
*   [docs/server.md](file:///usr/local/google/home/bpawan/workspace/official-v2/mcp-grpc-transport-py/docs/server.md)
*   [docs/client.md](file:///usr/local/google/home/bpawan/workspace/official-v2/mcp-grpc-transport-py/docs/client.md)

---

## Coding Standards & Conventions

### 1. Type Safety
*   **Strict Typing:** Type-hint all parameters and return types. Avoid using generic `Any` types where a specific union or protocol exists.
    *   *Correct:* `mcp_server: Server | MCPServer` (imported from `mcp.server`).
    *   *Correct:* `response_converter: Callable[[BaseModel], Message]` (where `Message` is imported from `google.protobuf.message`).
*   **Import Placement:** Keep imports at the top of the file to clarify dependencies and prevent runtime issues.

### 2. Pure Mapping in `convert.py`
*   Keep translation functions in `convert.py` pure and stateless. They should only translate models from Pydantic classes to Protobuf messages, and vice versa.
*   **Precision Loss Warning:** Be aware that Protobuf `Struct` maps all numbers to double-precision floats (`float` in Python). When writing handlers that expect integers (like port numbers or database IDs), always explicitly cast the deserialized dictionary values back to `int` (e.g. `int(params.arguments["a"])`).

### 3. Stateless Protocol Constraints
*   gRPC transport uses unary requests. Do not attempt to add persistent duplex backchannel communication (like server-to-client active requests).
*   If a client tries to send notifications or the server tries to call `send_raw_request`, raise `NoBackChannelError` immediately.

### 4. Lifecycles & Resource Cleanup
*   Always clean up resources cleanly.
*   **Client Dispatcher:** Must implement idempotent `close()` logic inside `finally` blocks (using a `_closed` sentinel flag) to prevent warnings during task group cancellation.
*   **Server Dispatcher:** Wrap the dispatcher `run()` wait loop in a `try...finally` block to clear servicer handlers (`self.servicer.set_handlers(None, None)`) when the runner is cancelled or stops. This ensures the servicer aborts incoming calls with `StatusCode.UNAVAILABLE` rather than calling stale callbacks.
