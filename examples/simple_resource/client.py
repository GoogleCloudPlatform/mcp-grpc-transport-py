"""Simple MCP gRPC Client example showcasing Resource usage."""

import asyncio
from mcp.client.session import ClientSession
from mcp_grpc_transport import GRPCClientDispatcher


async def main():
    address = "localhost:50052"
    dispatcher = GRPCClientDispatcher(address=address)

    print(f"Connecting to MCP gRPC Resource Server at {address}...")
    # Note: gRPC unary transport does not perform an MCP initialize handshake.
    async with ClientSession(dispatcher=dispatcher) as session:
        print("Connected.")

        # 1. List available resources
        print("\nListing resources...")
        resources = await session.list_resources()
        for resource in resources.resources:
            print(f"- {resource.uri}: {resource.name} ({resource.mime_type})")

        # 2. Read the static resource
        print("\nReading static resource 'mcp://resource/simple'...")
        contents = await session.read_resource("mcp://resource/simple")
        for content in contents.contents:
            print(f"Content: {content.text}")

        # 3. Read the templated user profile resource
        user = "alice"
        uri = f"mcp://hostname/user/{user}/profile"
        print(f"\nReading templated resource '{uri}'...")
        contents = await session.read_resource(uri)
        for content in contents.contents:
            print(f"Content: {content.text}")


if __name__ == "__main__":
    asyncio.run(main())
