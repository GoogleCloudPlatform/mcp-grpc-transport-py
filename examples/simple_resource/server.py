"""Simple MCP gRPC Server example showcasing Resources."""

import asyncio
from mcp.server.mcpserver import MCPServer
from mcp_grpc_transport import McpGrpcServer

# 1. Initialize high-level MCPServer
mcp = MCPServer("simple-resource-server")


# 2. Register a static text resource
@mcp.resource("mcp://resource/simple", mime_type="text/plain")
async def get_simple_resource() -> str:
    """A simple resource that returns text."""
    return "Hello from gRPC resource!"


# 3. Register a templated user profile resource
@mcp.resource("mcp://hostname/user/{user}/profile")
async def get_user_profile(user: str) -> str:
    """A templated resource for user profiles."""
    return f"Profile data for user: {user}"


async def main():
    address = "localhost:50052"
    
    # 4. Start the gRPC Server using the context manager
    async with McpGrpcServer(mcp, address=address) as app:
        print(f"MCP gRPC Resource Server running at {address}")
        print("Press Ctrl+C to stop.")
        await app.wait_for_termination()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping server...")
