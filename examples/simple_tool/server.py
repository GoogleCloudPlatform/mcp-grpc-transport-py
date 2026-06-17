"""Simple MCP gRPC Server example using high-level MCPServer."""

import asyncio
from mcp.server.mcpserver import MCPServer
from mcp_grpc_transport import McpGrpcServer

# 1. Initialize high-level MCPServer
mcp = MCPServer("simple-tool-server")


# 2. Register tools using the @mcp.tool() decorator
@mcp.tool()
async def calculate_sum(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


async def main():
    address = "localhost:50051"
    
    # 3. Start the gRPC Server using the context manager, passing our MCPServer
    async with McpGrpcServer(mcp, address=address) as app:
        print(f"MCP gRPC Server running at {address}")
        print("Press Ctrl+C to stop.")
        await app.wait_for_termination()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping server...")
