# Client Architecture

The `mcp-grpc-transport` client-side architecture uses a direct, stream-free implementation of the Model Context Protocol (MCP) client dispatcher, integrating directly into the SDK's V2 `ClientSession`.

```mermaid
graph TD
    Session[ClientSession (SDK Core)] -- 1. Call Session Method --> Dispatcher[GRPCClientDispatcher]
    Dispatcher -- 2. Map Params to Proto --> Protobuf[Protobuf Messages]
    Dispatcher -- 3. Invoke gRPC Call --> Stub[McpStub (gRPC Stub)]
    Stub <== gRPC Unary RPC ==> Server[gRPC Server]
```

## Key Components

### 1. `GRPCClientDispatcher` (`Dispatcher[TransportContext]`)
Implements the V2 SDK's `Dispatcher` protocol. It maps MCP client session commands directly to unary gRPC stubs.

*   **Stream-free design:** Unlike the default `JSONRPCDispatcher` which requires reading from and writing to async memory streams (with JSON serialization/framing), `GRPCClientDispatcher` bypasses the stream layer completely.
*   **Idempotency & Teardown:** Integrates a robust `close()` method that shuts down the managed gRPC channel. Uses a `_closed` flag to guarantee idempotency and avoid warnings during cancellation of the driving task group.
*   **Managed vs External Channels:** 
    *   **Managed Channel:** If only `address` is provided, the dispatcher creates and manages its own `grpc.aio.Channel` and closes it on shutdown.
    *   **External Channel:** If a pre-constructed `channel` is passed, the dispatcher leaves the channel's lifecycle management to the caller.

### 2. `convert.py` (Translation Layer)
Performs pure model mapping:
*   Translates V2 Python SDK snake_case models (e.g. `Tool`, `Resource`) into generated Protobuf equivalents.
*   Decodes/encodes binary assets (e.g. converting image/audio bytes back and forth from base64 strings used on the JSON wire format).

## Architectural Design Choices

### 1. No Initialize Handshake
The gRPC wire-level protobuf schema has no `Initialize` RPC and the transport intentionally does **not** perform any MCP-level handshake — no capability negotiation, no protocol-version exchange, no `serverInfo`. Callers must not invoke `session.initialize()` on a session bound to this dispatcher; doing so raises `METHOD_NOT_FOUND`. `ClientSession`'s other methods fall back to a default protocol version when init has not run, so list/read/call methods work as expected without it.

The server-side runs the SDK's `ServerRunner` with `stateless=True` for the same reason.

### 2. No Backchannel Support
Unary gRPC is strictly unidirectional. `GRPCClientDispatcher` does not support:
*   Inbound requests from the server.
*   Outbound notifications from the client to the server.

Any call to `session.send_notification(...)` raises `NoBackChannelError` immediately. This includes `notifications/initialized` — there is no handshake, so there is nothing to acknowledge.
