"""Conformance tests for gRPC dispatcher contract."""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
import logging
from typing import Any

import anyio
import grpc
import pytest

from mcp.shared.dispatcher import DispatchContext, OnNotify, OnRequest
from mcp.shared.exceptions import MCPError, NoBackChannelError
from mcp.shared.transport_context import TransportContext
import mcp.types as mcp_types

from mcp_grpc_transport import GRPCClientDispatcher
from mcp_grpc_transport.server import GRPCServerDispatcher, McpServicer
from mcp_grpc_transport_proto import mcp_pb2_grpc

logger = logging.getLogger(__name__)


@pytest.fixture
async def dispatcher_pair(free_port) -> AsyncIterator[tuple[GRPCClientDispatcher, GRPCServerDispatcher, grpc.aio.Server]]:
    address = f"localhost:{free_port}"
    grpc_server = grpc.aio.server()
    servicer = McpServicer()
    mcp_pb2_grpc.add_McpServicer_to_server(servicer, grpc_server)
    grpc_server.add_insecure_port(address)
    await grpc_server.start()
    
    server_dispatcher = GRPCServerDispatcher(servicer)
    client_dispatcher = GRPCClientDispatcher(address)
    
    yield client_dispatcher, server_dispatcher, grpc_server
    
    server_dispatcher.close()
    await client_dispatcher.close()
    await grpc_server.stop(0)


@asynccontextmanager
async def running_pair(
    client: GRPCClientDispatcher,
    server: GRPCServerDispatcher,
    *,
    server_on_request: OnRequest,
    server_on_notify: OnNotify,
) -> AsyncIterator[None]:
    async def mock_client_on_request(*args: Any) -> dict[str, Any]:
        return {}

    async def mock_client_on_notify(*args: Any) -> None:
        pass

    async with anyio.create_task_group() as tg:
        await tg.start(server.run, server_on_request, server_on_notify)
        # Client dispatcher run just parks, but we need to start it to align with protocol.
        # We pass proper async mock callables to satisfy OnRequest/OnNotify type requirements.
        await tg.start(client.run, mock_client_on_request, mock_client_on_notify)
        try:
            yield
        finally:
            tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_send_raw_request_success(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(
        ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        assert method == "tools/list"
        # Return a valid serialized ListToolsResult
        return {"tools": [{"name": "test", "inputSchema": {"type": "object"}}]}
        
    async def on_notify(ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None) -> None:
        pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        res = await client.send_raw_request("tools/list", {})
        assert "tools" in res
        assert res["tools"][0]["name"] == "test"


@pytest.mark.anyio
async def test_send_raw_request_mcp_error(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(
        ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        raise MCPError(code=mcp_types.INVALID_PARAMS, message="bad params")
        
    async def on_notify(ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None) -> None:
        pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(MCPError) as exc:
            await client.send_raw_request("tools/list", {})
        # Note: gRPC error mapping maps INVALID_ARGUMENT to INVALID_PARAMS
        assert exc.value.error.code == mcp_types.INVALID_PARAMS
        assert "bad params" in exc.value.message


@pytest.mark.anyio
async def test_send_raw_request_generic_error(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(
        ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        raise ValueError("crash")
        
    async def on_notify(ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None) -> None:
        pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(MCPError) as exc:
            await client.send_raw_request("tools/list", {})
        assert exc.value.error.code == mcp_types.INTERNAL_ERROR
        assert "crash" in exc.value.message


@pytest.mark.anyio
async def test_server_to_client_request_raises_no_backchannel(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(
        ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        # Server tries to call client (backchannel)
        assert ctx.can_send_request is False
        with pytest.raises(NoBackChannelError):
            await ctx.send_raw_request("sampling/createMessage", {})
        # Return something to complete the call
        return {"tools": []}
        
    async def on_notify(ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None) -> None:
        pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        await client.send_raw_request("tools/list", {})


@pytest.mark.anyio
async def test_client_notify_always_raises_no_backchannel(dispatcher_pair):
    """Every client notification — including notifications/initialized — is rejected.

    The transport does no MCP-level handshake, so there is no notification to
    drop politely; all of them violate the unary contract.
    """
    client, server, _ = dispatcher_pair

    async def on_request(ctx, m, p): return {}
    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(NoBackChannelError):
            await client.notify("notifications/initialized", {})
        with pytest.raises(NoBackChannelError):
            await client.notify("notifications/roots/list_changed", {})


@pytest.mark.anyio
async def test_initialize_method_is_not_handled(dispatcher_pair):
    """`send_raw_request("initialize", ...)` must fail; the transport does no handshake."""
    from mcp.shared.exceptions import MCPError
    client, server, _ = dispatcher_pair

    async def on_request(ctx, m, p): return {}
    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(MCPError) as exc:
            await client.send_raw_request("initialize", {})
        assert exc.value.error.code == mcp_types.METHOD_NOT_FOUND


@pytest.mark.anyio
async def test_send_raw_request_timeout(dispatcher_pair):
    client, server, _ = dispatcher_pair

    async def on_request(
        ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        # Sleep longer than the client's 0.1s timeout so the deadline fires.
        await anyio.sleep(1.0)
        return {"tools": []}

    async def on_notify(ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None) -> None:
        pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(MCPError) as exc:
            await client.send_raw_request("tools/list", {}, {"timeout": 0.1})
        assert exc.value.error.code == mcp_types.REQUEST_TIMEOUT


@pytest.mark.anyio
async def test_meta_round_trips_to_server(dispatcher_pair):
    """`_meta` supplied on the client must reach the server's handler params."""
    client, server, _ = dispatcher_pair
    seen_params: dict[str, Any] = {}

    async def on_request(ctx, method, params):
        seen_params.update(params or {})
        return {"tools": []}

    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        await client.send_raw_request("tools/list", {"_meta": {"trace_id": "abc-123"}})

    assert seen_params.get("_meta") == {"trace_id": "abc-123"}


@pytest.mark.anyio
async def test_error_preserves_original_mcp_code(dispatcher_pair):
    """All three INVALID_ARGUMENT-mapped MCP codes must round-trip exactly."""
    client, server, _ = dispatcher_pair
    raise_code: list[int] = [mcp_types.PARSE_ERROR]

    async def on_request(ctx, method, params):
        raise MCPError(code=raise_code[0], message="boom")

    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        for code in (mcp_types.PARSE_ERROR, mcp_types.INVALID_REQUEST, mcp_types.INVALID_PARAMS):
            raise_code[0] = code
            with pytest.raises(MCPError) as exc:
                await client.send_raw_request("tools/list", {})
            assert exc.value.error.code == code, f"expected {code}, got {exc.value.error.code}"


@pytest.mark.anyio
async def test_server_dispatch_context_notify_raises_no_backchannel(dispatcher_pair):
    """ctx.notify must raise NoBackChannelError (#8 — was previously a silent drop)."""
    client, server, _ = dispatcher_pair

    async def on_request(ctx, method, params):
        with pytest.raises(NoBackChannelError):
            await ctx.notify("notifications/progress", {})
        return {"tools": []}

    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        await client.send_raw_request("tools/list", {})


@pytest.mark.anyio
async def test_server_dispatcher_notify_raises_no_backchannel(dispatcher_pair):
    """The dispatcher-level notify path must also reject backchannel attempts."""
    client, server, _ = dispatcher_pair
    with pytest.raises(NoBackChannelError):
        await server.notify("notifications/progress", {})


def test_client_requires_address_or_channel():
    """Constructing a dispatcher with neither address nor channel must fail loudly."""
    from mcp_grpc_transport import GRPCClientDispatcher
    with pytest.raises(ValueError, match="address.*channel"):
        GRPCClientDispatcher()

