# Version Negotiation

This document describes how protocol version negotiation is handled in the MCP
Python SDK's gRPC transport. Version negotiation ensures that clients and
servers can communicate effectively even if they support different sets of MCP
protocol versions.

## 1. Supported Protocol Versions

The set of supported MCP protocol versions is defined in
`mcp/shared/version.py`:

```python
# mcp/shared/version.py
from mcp.types import LATEST_PROTOCOL_VERSION

SUPPORTED_PROTOCOL_VERSIONS: list[str] = ["2024-11-05", "2025-03-26", LATEST_PROTOCOL_VERSION]
```

`LATEST_PROTOCOL_VERSION` is the most recent version the SDK supports.

## 2. Client-Side Version Handling

The client-side gRPC transport session, implemented in
`mcp_grpc_transport/client/grpc_client_session.py`,
manages the negotiated protocol version.

### Sending the Protocol Version

When a client makes a unary RPC call (e.g., `ListTools`, `ListResources`,
`ReadResource`), the `GRPCClientSession` includes the `mcp-protocol-version` in
the gRPC request metadata. Initially, this is set to `LATEST_PROTOCOL_VERSION`.

```python
# From mcp_grpc_transport/client/grpc_client_session.py
async def _call_unary_rpc_with_version_negotiation(
    self, rpc_method: Any, request: Any, timeout: float | None = None,
    metadata: list[tuple[str, str]] | None = None
) -> Any:
    # ...
    response = await rpc_method(
        request,
        metadata=(metadata + self.get_version_metadata()),
        timeout=timeout,
    )
    # ...
```

### Handling Version Mismatch

If the server does not support the protocol version sent by the client, it will
respond with a `grpc.StatusCode.UNIMPLEMENTED` error. The client's
`_check_and_update_version` method is designed to catch and handle this:

```python
# From mcp_grpc_transport/client/grpc_client_session.py
def _check_and_update_version(self, rpc_error: grpc.aio.AioRpcError) -> bool:
    if rpc_error.code() is grpc.StatusCode.UNIMPLEMENTED:
        initial_metadata = rpc_error.initial_metadata()
        negotiated_version = version_utils.get_metadata_value(
            initial_metadata, version_utils.MCP_PROTOCOL_VERSION_KEY
        )

        if (
            negotiated_version is not None
            and negotiated_version in version_utils.SUPPORTED_PROTOCOL_VERSIONS
        ):
            # Server provided a supported version, update and retry
            self.negotiated_version = negotiated_version
            return True
    return False
```

If the server's `UNIMPLEMENTED` error includes metadata with a supported
`mcp-protocol-version`, the client updates its `self.negotiated_version` and
retries the RPC with the newly negotiated version.

## 3. Server-Side Version Checking

The MCP gRPC server implementation in
`mcp_grpc_transport/server/grpc_server.py` performs
protocol version checks at the beginning of each RPC handler.

### Protocol Version Verification

Each of the `McpServicer` RPC methods (`ListResources`, `ListTools`, `CallTool`,
etc.) calls `version_utils.verify_protocol_version_from_metadata(context)`.

```python
# From mcp_grpc_transport/server/grpc_server.py
async def CallTool(
    self,
    request: mcp_messages_pb2.CallToolRequest,
    context: grpc.aio.ServicerContext,
):
    await version_utils.verify_protocol_version_from_metadata(context)
    # ... proceed with RPC ...
```

This function, defined in
`mcp_grpc_transport/utils/version_utils.py`, performs the
following steps:

1.  **Extract Version:** It extracts the value of the `mcp-protocol-version` key
    from the incoming request's gRPC metadata.
2.  **Validate Version:** It checks if the extracted version is present in the
    list of supported protocol versions.
3.  **Handle Missing/Unsupported Version:**
    *   If the `mcp-protocol-version` is missing or not supported, the server
        sends initial metadata back to the client. This metadata includes the
        server's `LATEST_PROTOCOL_VERSION`.
    *   The server then aborts the RPC with `grpc.StatusCode.UNIMPLEMENTED`,
        providing a message indicating the unsupported version and listing the
        versions it *does* support.
4.  **Handle Supported Version:** If the client's provided version is supported,
    the server sends initial metadata back to the client, echoing the client's
    `mcp-protocol-version`, and allows the RPC call to proceed.

This collaborative process ensures that both client and server can successfully
negotiate a common protocol version to use for their communication.
