# Server Architecture

The `mcp-grpc-transport` server-side architecture provides a stateless, unary gRPC-based implementation of the Model Context Protocol (MCP) server transport, integrating seamlessly with the Python SDK V2.

```mermaid
graph TD
    Client[Client Session / gRPC Stub] <== gRPC ==> Servicer[McpServicer]
    Servicer -- 1. Receive RPC Request --> Dispatcher[GRPCServerDispatcher]
    Dispatcher -- 2. on_request --> Runner[ServerRunner (SDK Core)]
    Runner -- 3. Dispatch to Server --> MCPServer[MCPServer / Server]
    MCPServer -- 4. Execute Handler --> Callback[User Callback / @mcp.tool]
```

## Key Components

### 1. `McpGrpcServer` (Orchestrator)
The top-level orchestrator that manages the lifecycle of the gRPC server and the SDK's `ServerRunner`.

*   **Managed Mode:** Creates and manages its own internal `grpc.aio.Server` instance, binding to the provided `address`.
*   **Unmanaged Mode:** Accepts an externally created `grpc.aio.Server` (via `server=` argument) and only manages the SDK runner loop. Useful for embedding MCP into an existing gRPC application.
*   **Context Manager Interface:** Implements `__aenter__` and `__aexit__` to cleanly orchestrate the startup and teardown of the server and task groups, ensuring clean cancellation of active runners on exit.

### 2. `McpServicer` (`mcp_pb2_grpc.McpServicer`)
The low-level gRPC servicer implementation. It maps incoming Protobuf RPC calls (e.g. `ListTools`, `CallTool`) into the transport dispatcher's `_on_request` or `_on_notify` callbacks.

*   **Pydantic / Protobuf Bridge:** Handles the serialization boundary. It receives Protobuf messages, translates them to JSON-like dictionaries, validates them using SDK Pydantic models (which maps wire camelCase keys to Python snake_case attributes), and then converts the resulting Python models back to Protobuf messages.
*   **Handler Lifecycle:** To prevent calling stale handlers when the runner is stopped (e.g. during runner teardown on a server that remains running), `McpServicer` exposes `set_handlers()` to register/clear callbacks. When callbacks are cleared, incoming calls are aborted with `StatusCode.UNAVAILABLE` ("Server not ready").

### 3. `GRPCServerDispatcher` (`Dispatcher[TransportContext]`)
Implements the V2 SDK's `Dispatcher` protocol. It registers the SDK's `on_request` and `on_notify` callbacks onto the `McpServicer`.

*   **Stateless gRPC Loop:** Since gRPC handles concurrent request dispatching natively, the dispatcher's `run()` method does not run an active read loop. It simply parks on a close event waiting to be shut down.
*   **No Backchannel:** The dispatcher enforces a strict unary contract by returning `False` for `can_send_request` and raising `NoBackChannelError` on any attempt by the server to send outbound requests or active notifications to the client.

## Request Execution Flow

1.  **RPC Arrival:** A client makes a gRPC call (e.g. `ListTools`).
2.  **Servicer Handling:** `McpServicer._handle_rpc` is invoked. It extracts arguments, converting them to generic dictionary parameters.
3.  **Dispatcher Call:** The servicer calls `_on_request()` on the dispatcher's registered callback.
4.  **SDK Dispatch:** The SDK's `ServerRunner` executes the handler registered on the `MCPServer`/`Server` class.
5.  **Pydantic Validation:** The return dictionary from the handler is validated against the expected V2 Pydantic model (`result_model.model_validate`), adjusting aliases.
6.  **Protobuf Serialization:** The validated model is converted into the corresponding Protobuf response message using the converters in `convert.py` and returned.
