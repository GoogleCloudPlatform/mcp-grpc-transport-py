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
async def test_client_notify_drops_initialized(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(ctx, m, p): return {}
    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        # Should not raise
        await client.notify("notifications/initialized", {})


@pytest.mark.anyio
async def test_client_notify_raises_no_backchannel_for_others(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(ctx, m, p): return {}
    async def on_notify(ctx, m, p): pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(NoBackChannelError):
            await client.notify("notifications/roots/list_changed", {})


@pytest.mark.anyio
async def test_send_raw_request_timeout(dispatcher_pair):
    client, server, _ = dispatcher_pair
    
    async def on_request(
        ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        await anyio.sleep(1.0)
        return {"tools": []}
        
    async def on_notify(ctx: DispatchContext[TransportContext], method: str, params: Mapping[str, Any] | None) -> None:
        pass

    async with running_pair(client, server, server_on_request=on_request, server_on_notify=on_notify):
        with pytest.raises(MCPError) as exc:
            # Short timeout of 0.1s
            await client.send_raw_request("tools/list", {}, {"timeout": 0.1})
        assert exc.value.error.code == mcp_types.REQUEST_TIMEOUT

