"""Conformance tests for gRPC dispatcher contract."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest import IsolatedAsyncioTestCase

import anyio
import grpc
from absl.testing import absltest
from mcp.shared.dispatcher import OnNotify, OnRequest
from mcp.shared.exceptions import MCPError, NoBackChannelError
import mcp.types as mcp_types

from mcp_grpc_transport import GRPCClientDispatcher
from mcp_grpc_transport.server import GRPCServerDispatcher, McpServicer
from mcp_grpc_transport_proto import mcp_pb2_grpc

from tests.helpers import find_free_port


@asynccontextmanager
async def running_pair(
    client: GRPCClientDispatcher,
    server: GRPCServerDispatcher,
    *,
    server_on_request: OnRequest,
    server_on_notify: OnNotify,
) -> AsyncIterator[None]:
    """Drive both dispatchers under one task group and tear them down on exit."""

    async def mock_client_on_request(*args: Any) -> dict[str, Any]:
        return {}

    async def mock_client_on_notify(*args: Any) -> None:
        pass

    async with anyio.create_task_group() as tg:
        await tg.start(server.run, server_on_request, server_on_notify)
        await tg.start(client.run, mock_client_on_request, mock_client_on_notify)
        try:
            yield
        finally:
            tg.cancel_scope.cancel()


class DispatcherConformanceTest(absltest.TestCase, IsolatedAsyncioTestCase):
    """Async tests share a fresh client/server dispatcher pair per case.

    Mixes `absltest.TestCase` (for richer assertions like `assertLen`) with
    `IsolatedAsyncioTestCase` (for native async test method support — absl
    doesn't ship an async-aware TestCase).
    """

    async def asyncSetUp(self) -> None:
        port = find_free_port()
        self.address = f"localhost:{port}"
        self.grpc_server = grpc.aio.server()
        self.servicer = McpServicer()
        mcp_pb2_grpc.add_McpServicer_to_server(self.servicer, self.grpc_server)
        self.grpc_server.add_insecure_port(self.address)
        await self.grpc_server.start()

        self.server_dispatcher = GRPCServerDispatcher(self.servicer)
        self.client_dispatcher = GRPCClientDispatcher(self.address)

    async def asyncTearDown(self) -> None:
        self.server_dispatcher.close()
        await self.client_dispatcher.close()
        await self.grpc_server.stop(0)

    async def test_send_raw_request_success(self):
        async def on_request(ctx, method, params):
            self.assertEqual(method, "tools/list")
            return {"tools": [{"name": "test", "inputSchema": {"type": "object"}}]}

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            res = await self.client_dispatcher.send_raw_request("tools/list", {})

        self.assertIn("tools", res)
        self.assertEqual(res["tools"][0]["name"], "test")

    async def test_send_raw_request_mcp_error(self):
        async def on_request(ctx, method, params):
            raise MCPError(code=mcp_types.INVALID_PARAMS, message="bad params")

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            with self.assertRaises(MCPError) as cm:
                await self.client_dispatcher.send_raw_request("tools/list", {})

        self.assertEqual(cm.exception.error.code, mcp_types.INVALID_PARAMS)
        self.assertIn("bad params", cm.exception.message)

    async def test_send_raw_request_generic_error(self):
        async def on_request(ctx, method, params):
            raise ValueError("crash")

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            with self.assertRaises(MCPError) as cm:
                await self.client_dispatcher.send_raw_request("tools/list", {})

        self.assertEqual(cm.exception.error.code, mcp_types.INTERNAL_ERROR)
        self.assertIn("crash", cm.exception.message)

    async def test_server_to_client_request_raises_no_backchannel(self):
        async def on_request(ctx, method, params):
            self.assertFalse(ctx.can_send_request)
            with self.assertRaises(NoBackChannelError):
                await ctx.send_raw_request("sampling/createMessage", {})
            return {"tools": []}

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            await self.client_dispatcher.send_raw_request("tools/list", {})

    async def test_client_notify_always_raises(self):
        """Unary gRPC has no backchannel; the dispatcher rejects every notify."""

        async def on_request(ctx, m, p):
            return {}

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            with self.assertRaises(NoBackChannelError):
                await self.client_dispatcher.notify("notifications/initialized", {})
            with self.assertRaises(NoBackChannelError):
                await self.client_dispatcher.notify("notifications/roots/list_changed", {})

    async def test_send_raw_request_timeout(self):
        async def on_request(ctx, method, params):
            # Sleep longer than the client's 0.1s timeout so the deadline fires.
            await anyio.sleep(1.0)
            return {"tools": []}

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            with self.assertRaises(MCPError) as cm:
                await self.client_dispatcher.send_raw_request("tools/list", {}, {"timeout": 0.1})

        self.assertEqual(cm.exception.error.code, mcp_types.REQUEST_TIMEOUT)

    async def test_meta_round_trips_to_server(self):
        """`_meta` supplied on the client must reach the server's handler params."""
        seen_params: dict[str, Any] = {}

        async def on_request(ctx, method, params):
            seen_params.update(params or {})
            return {"tools": []}

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            await self.client_dispatcher.send_raw_request(
                "tools/list", {"_meta": {"trace_id": "abc-123"}}
            )

        self.assertEqual(seen_params.get("_meta"), {"trace_id": "abc-123"})

    async def test_error_preserves_original_mcp_code(self):
        """All three INVALID_ARGUMENT-mapped MCP codes must round-trip exactly."""
        raise_code: list[int] = [mcp_types.PARSE_ERROR]

        async def on_request(ctx, method, params):
            raise MCPError(code=raise_code[0], message="boom")

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            for code in (mcp_types.PARSE_ERROR, mcp_types.INVALID_REQUEST, mcp_types.INVALID_PARAMS):
                raise_code[0] = code
                with self.assertRaises(MCPError) as cm:
                    await self.client_dispatcher.send_raw_request("tools/list", {})
                self.assertEqual(cm.exception.error.code, code, f"expected {code}")

    async def test_server_dispatch_context_notify_raises_no_backchannel(self):
        """ctx.notify must raise NoBackChannelError (was previously a silent drop)."""

        async def on_request(ctx, method, params):
            with self.assertRaises(NoBackChannelError):
                await ctx.notify("notifications/progress", {})
            return {"tools": []}

        async def on_notify(ctx, m, p):
            pass

        async with running_pair(
            self.client_dispatcher, self.server_dispatcher,
            server_on_request=on_request, server_on_notify=on_notify,
        ):
            await self.client_dispatcher.send_raw_request("tools/list", {})

    async def test_server_dispatcher_notify_raises_no_backchannel(self):
        """The dispatcher-level notify path also rejects backchannel attempts."""
        with self.assertRaises(NoBackChannelError):
            await self.server_dispatcher.notify("notifications/progress", {})


class ClientConstructionTest(absltest.TestCase):

    def test_requires_address_or_channel(self):
        """Constructing a dispatcher with neither address nor channel must fail loudly."""
        with self.assertRaisesRegex(ValueError, "address.*channel"):
            GRPCClientDispatcher()


if __name__ == "__main__":
    absltest.main()
