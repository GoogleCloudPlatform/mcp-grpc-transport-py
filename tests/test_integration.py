"""Loopback integration tests using McpGrpcServer and GRPCClientDispatcher."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest import IsolatedAsyncioTestCase

import grpc
from absl.testing import absltest
from mcp.client.session import ClientSession
from mcp.server.lowlevel.server import Server
from mcp.shared.exceptions import MCPError
import mcp.types as mcp_types

from mcp_grpc_transport import GRPCClientDispatcher, McpGrpcServer

from tests.helpers import find_free_port


@asynccontextmanager
async def run_server(server: Server, address: str) -> AsyncIterator[str]:
    async with McpGrpcServer(server, address=address):
        yield address


class IntegrationTest(absltest.TestCase, IsolatedAsyncioTestCase):
    """Async integration tests.

    Inherits from `absltest.TestCase` (for `assertLen` and friends) AND
    `IsolatedAsyncioTestCase` (for `async def test_*` support — absl doesn't
    ship an async-aware TestCase).
    """


    def setUp(self) -> None:
        self.address = f"localhost:{find_free_port()}"

    async def test_tools_round_trip(self):
        async def list_tools(ctx, params):
            return mcp_types.ListToolsResult(
                tools=[
                    mcp_types.Tool(
                        name="add",
                        description="add numbers",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "a": {"type": "integer"},
                                "b": {"type": "integer"},
                            },
                            "required": ["a", "b"],
                        },
                    )
                ]
            )

        async def call_tool(ctx, params):
            if params.name == "add":
                a = int(params.arguments.get("a", 0))
                b = int(params.arguments.get("b", 0))
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=str(a + b))]
                )
            raise ValueError(f"Unknown tool: {params.name}")

        server = Server("test-server", on_list_tools=list_tools, on_call_tool=call_tool)

        async with run_server(server, self.address) as address:
            dispatcher = GRPCClientDispatcher(address)
            async with ClientSession(dispatcher=dispatcher) as session:
                tools = await session.list_tools()
                self.assertLen(tools.tools, 1)
                self.assertEqual(tools.tools[0].name, "add")

                res = await session.call_tool("add", {"a": 2, "b": 3})
                self.assertFalse(res.is_error)
                self.assertLen(res.content, 1)
                self.assertEqual(res.content[0].text, "5")

    async def test_resources_round_trip(self):
        async def list_resources(ctx, params):
            return mcp_types.ListResourcesResult(
                resources=[
                    mcp_types.Resource(uri="test://data", name="data", mime_type="text/plain"),
                ]
            )

        async def read_resource(ctx, params):
            if str(params.uri) == "test://data":
                return mcp_types.ReadResourceResult(
                    contents=[
                        mcp_types.TextResourceContents(
                            uri=params.uri, mime_type="text/plain", text="resource contents",
                        ),
                    ]
                )
            raise ValueError(f"Resource not found: {params.uri}")

        server = Server(
            "test-server", on_list_resources=list_resources, on_read_resource=read_resource
        )

        async with run_server(server, self.address) as address:
            dispatcher = GRPCClientDispatcher(address)
            async with ClientSession(dispatcher=dispatcher) as session:
                resources = await session.list_resources()
                self.assertLen(resources.resources, 1)
                self.assertEqual(resources.resources[0].name, "data")

                res = await session.read_resource("test://data")
                self.assertLen(res.contents, 1)
                self.assertEqual(res.contents[0].text, "resource contents")

    async def test_resource_templates(self):
        async def list_resource_templates(ctx, params):
            return mcp_types.ListResourceTemplatesResult(
                resource_templates=[
                    mcp_types.ResourceTemplate(
                        uri_template="test://template/{name}",
                        name="template",
                        mime_type="text/plain",
                    ),
                ]
            )

        server = Server("test-server", on_list_resource_templates=list_resource_templates)

        async with run_server(server, self.address) as address:
            dispatcher = GRPCClientDispatcher(address)
            async with ClientSession(dispatcher=dispatcher) as session:
                templates = await session.list_resource_templates()
                self.assertLen(templates.resource_templates, 1)
                self.assertEqual(templates.resource_templates[0].name, "template")

    async def test_error_propagation_preserves_mcp_code(self):
        async def list_tools(ctx, params):
            return mcp_types.ListToolsResult(
                tools=[mcp_types.Tool(name="fail", input_schema={"type": "object"})]
            )

        async def call_tool(ctx, params):
            if params.name == "fail":
                raise MCPError(code=mcp_types.INVALID_PARAMS, message="planned failure")
            raise ValueError("unknown tool")

        server = Server("test-server", on_list_tools=list_tools, on_call_tool=call_tool)

        async with run_server(server, self.address) as address:
            dispatcher = GRPCClientDispatcher(address)
            async with ClientSession(dispatcher=dispatcher) as session:
                with self.assertRaises(MCPError) as cm:
                    await session.call_tool("fail", {})

                # Original MCP code (INVALID_PARAMS) is preserved via trailing metadata,
                # not lossily reconstructed from gRPC's INVALID_ARGUMENT.
                self.assertEqual(cm.exception.error.code, mcp_types.INVALID_PARAMS)
                self.assertIn("planned failure", cm.exception.message)

    async def test_mcp_server_high_level_decorator_api(self):
        """End-to-end with the high-level MCPServer (decorator API).

        Exercises the isinstance-based `_lowlevel_server` extraction path.
        """
        from mcp.server.mcpserver import MCPServer

        mcp = MCPServer("hl-test-server")

        @mcp.tool()
        async def echo(text: str) -> str:
            return text

        async with McpGrpcServer(mcp, address=self.address):
            dispatcher = GRPCClientDispatcher(self.address)
            async with ClientSession(dispatcher=dispatcher) as session:
                tools = await session.list_tools()
                self.assertTrue(any(t.name == "echo" for t in tools.tools))

                res = await session.call_tool("echo", {"text": "hi"})
                self.assertEqual(res.content[0].text, "hi")

    async def test_stale_handlers_cleared(self):
        grpc_server = grpc.aio.server()

        async def list_tools(ctx, params):
            return mcp_types.ListToolsResult(tools=[])

        server = Server("test-server", on_list_tools=list_tools)
        app = McpGrpcServer(server, server=grpc_server)

        grpc_server.add_insecure_port(self.address)
        await grpc_server.start()

        try:
            # 1. Runner active: handlers are registered on the servicer.
            async with app:
                dispatcher = GRPCClientDispatcher(self.address)
                async with ClientSession(dispatcher=dispatcher) as session:
                    tools = await session.list_tools()
                    self.assertLen(tools.tools, 0)

            # 2. Exited McpGrpcServer context: GRPCServerDispatcher.run's finally
            # block clears the servicer handlers, but the gRPC server is still running.
            dispatcher2 = GRPCClientDispatcher(self.address)
            async with ClientSession(dispatcher=dispatcher2) as session2:
                # This call should be rejected by the servicer with UNAVAILABLE.
                with self.assertRaises(MCPError) as cm:
                    await session2.list_tools()
                self.assertEqual(cm.exception.error.code, mcp_types.INTERNAL_ERROR)
                self.assertIn("Server not ready", cm.exception.message)
        finally:
            await grpc_server.stop(grace=None)


if __name__ == "__main__":
    absltest.main()
