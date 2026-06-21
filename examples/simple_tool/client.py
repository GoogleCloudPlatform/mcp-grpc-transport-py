"""Simple MCP gRPC Client example."""

import asyncio
from mcp.client.session import ClientSession
from mcp_grpc_transport import GRPCClientDispatcher


async def main():
    address = "localhost:50051"
    dispatcher = GRPCClientDispatcher(address=address)

    print(f"Connecting to MCP gRPC Server at {address}...")
    # Note: gRPC unary transport does not perform an MCP initialize handshake.
    # Do not call `session.initialize()` here — methods can be invoked directly.
    async with ClientSession(dispatcher=dispatcher) as session:
        print("Connected.")

        # List tools
        tools = await session.list_tools()
        print("\nAvailable Tools:")
        for tool in tools.tools:
            print(f"- {tool.name}: {tool.description}")

        # Call tool
        print("\nCalling calculate_sum with a=10, b=20...")
        result = await session.call_tool("calculate_sum", {"a": 10, "b": 20})
        print(f"Result: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
