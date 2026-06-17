"""Loopback integration tests using McpGrpcServer and GRPCClientDispatcher."""

import asyncio
from collections.abc import AsyncIterator
import socket
from contextlib import closing, asynccontextmanager
import grpc
import pytest

from mcp.server.lowlevel.server import Server
from mcp.client.session import ClientSession
from mcp.shared.exceptions import MCPError
import mcp.types as mcp_types
from mcp_grpc_transport import GRPCClientDispatcher, McpGrpcServer


def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@asynccontextmanager
async def run_server(server: Server) -> AsyncIterator[str]:
    port = find_free_port()
    address = f"localhost:{port}"
    async with McpGrpcServer(server, address=address):
        yield address


@pytest.mark.anyio
async def test_integration_tools():
    # 1. Define handlers
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
                            "b": {"type": "integer"}
                        },
                        "required": ["a", "b"]
                    }
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

    # 2. Create Server with handlers
    server = Server(
        "test-server",
        on_list_tools=list_tools,
        on_call_tool=call_tool
    )

    # 3. Run Server and Client
    async with run_server(server) as address:
        dispatcher = GRPCClientDispatcher(address)
        async with ClientSession(dispatcher=dispatcher) as session:
            await session.initialize()
            
            # Test list_tools
            tools = await session.list_tools()
            assert len(tools.tools) == 1
            assert tools.tools[0].name == "add"
            
            # Test call_tool
            res = await session.call_tool("add", {"a": 2, "b": 3})
            assert res.is_error is False
            assert len(res.content) == 1
            assert res.content[0].text == "5"


@pytest.mark.anyio
async def test_integration_resources():
    async def list_resources(ctx, params):
        return mcp_types.ListResourcesResult(
            resources=[
                mcp_types.Resource(
                    uri="test://data",
                    name="data",
                    mime_type="text/plain"
                )
            ]
        )
        
    async def read_resource(ctx, params):
        if str(params.uri) == "test://data":
            return mcp_types.ReadResourceResult(
                contents=[
                    mcp_types.TextResourceContents(
                        uri=params.uri,
                        mime_type="text/plain",
                        text="resource contents"
                    )
                ]
            )
        raise ValueError(f"Resource not found: {params.uri}")

    server = Server(
        "test-server",
        on_list_resources=list_resources,
        on_read_resource=read_resource
    )

    async with run_server(server) as address:
        dispatcher = GRPCClientDispatcher(address)
        async with ClientSession(dispatcher=dispatcher) as session:
            await session.initialize()
            
            # Test list_resources
            resources = await session.list_resources()
            assert len(resources.resources) == 1
            assert resources.resources[0].name == "data"
            
            # Test read_resource
            res = await session.read_resource("test://data")
            assert len(res.contents) == 1
            assert res.contents[0].text == "resource contents"


@pytest.mark.anyio
async def test_integration_resource_templates():
    async def list_resource_templates(ctx, params):
        return mcp_types.ListResourceTemplatesResult(
            resource_templates=[
                mcp_types.ResourceTemplate(
                    uri_template="test://template/{name}",
                    name="template",
                    mime_type="text/plain"
                )
            ]
        )

    server = Server(
        "test-server",
        on_list_resource_templates=list_resource_templates
    )

    async with run_server(server) as address:
        dispatcher = GRPCClientDispatcher(address)
        async with ClientSession(dispatcher=dispatcher) as session:
            await session.initialize()
            
            # Test list_resource_templates
            templates = await session.list_resource_templates()
            assert len(templates.resource_templates) == 1
            assert templates.resource_templates[0].name == "template"


@pytest.mark.anyio
async def test_integration_error_propagation():
    async def list_tools(ctx, params):
        return mcp_types.ListToolsResult(
            tools=[mcp_types.Tool(name="fail", input_schema={"type": "object"})]
        )
        
    async def call_tool(ctx, params):
        if params.name == "fail":
            # Throw standard MCPError
            raise MCPError(code=mcp_types.INVALID_PARAMS, message="planned failure")
        raise ValueError("unknown tool")

    server = Server(
        "test-server",
        on_list_tools=list_tools,
        on_call_tool=call_tool
    )

    async with run_server(server) as address:
        dispatcher = GRPCClientDispatcher(address)
        async with ClientSession(dispatcher=dispatcher) as session:
            await session.initialize()
            
            with pytest.raises(MCPError) as exc:
                await session.call_tool("fail", {})
            assert exc.value.error.code == mcp_types.INVALID_PARAMS
            assert "planned failure" in exc.value.message


@pytest.mark.anyio
async def test_integration_stale_handlers_cleared():
    grpc_server = grpc.aio.server()
    async def list_tools(ctx, params):
        return mcp_types.ListToolsResult(tools=[])

    server = Server("test-server", on_list_tools=list_tools)
    app = McpGrpcServer(server, server=grpc_server)

    port = find_free_port()
    address = f"localhost:{port}"
    grpc_server.add_insecure_port(address)
    await grpc_server.start()

    try:
        # 1. Start McpGrpcServer managing only the runner (external gRPC server)
        async with app:
            # Runner is active, handlers are registered on the servicer.
            dispatcher = GRPCClientDispatcher(address)
            async with ClientSession(dispatcher=dispatcher) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 0

        # 2. Exited McpGrpcServer context. The runner is cancelled, and 
        # GRPCServerDispatcher.run's finally block should clear the servicer handlers.
        # But the gRPC server is still running.

        dispatcher2 = GRPCClientDispatcher(address)
        async with ClientSession(dispatcher=dispatcher2) as session2:
            await session2.initialize() # Mocked client side
            # This call should now be rejected by the servicer with UNAVAILABLE
            with pytest.raises(MCPError) as exc_info:
                await session2.list_tools()
            assert exc_info.value.error.code == mcp_types.INTERNAL_ERROR
            assert "Server not ready" in exc_info.value.message
    finally:
        await grpc_server.stop(grace=None)

