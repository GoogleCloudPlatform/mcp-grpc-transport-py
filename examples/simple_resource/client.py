"""Example client for calling the MCP gRPC server simple resource."""

import asyncio

from absl import app
from absl import flags
import mcp
from mcp_grpc_transport.client import grpc_client_session

_SERVER_HOST = flags.DEFINE_string("server_host", "localhost", "Server host")
_SERVER_PORT = flags.DEFINE_integer("server_port", 50052, "Server port")


async def call_server(host: str, port: int):
  """Call the MCP gRPCserver and print the results."""
  print("========================================")
  print(" MCP gRPC Simple Resource and Resource Template Client Example")
  print("========================================")
  session = grpc_client_session.GRPCClientSession(target=f"{host}:{port}")
  print(f"➡️ Connecting to server: {host}:{port}")

  try:
    print("\n========================================")
    print("➡️ Listing available resources...")
    print("========================================")
    resources = await session.list_resources()
    print("✅ Received resource list. Available resources:")
    print(f"{resources}")

    print("\n========================================")
    print("➡️ Listing available resource templates...")
    print("========================================")
    templates = await session.list_resource_templates()
    print("✅ Received resource template list. Available templates:")
    for template in templates.resourceTemplates:
      print(f"  {template.uriTemplate}: {template.description}")

    print("\n========================================")
    print("➡️ Reading non-existent resource 'mcp://resource/non_existent'...")
    print("========================================")
    try:
      await session.read_resource("mcp://resource/non_existent")
    except mcp.McpError as e:
      print(
          "❌ Received expected failure response for non-existent resource:"
          f"\n   {e}"
      )

    print("\n========================================")
    print("➡️ Reading resource 'mcp://resource/simple'...")
    print("========================================")
    resource_content = await session.read_resource("mcp://resource/simple")
    print(f"✅ Received resource content:\n   {resource_content}")
    print("========================================")

    print("\n========================================")
    print("➡️ Reading user profile template resource...")
    print("========================================")
    profile_content = await session.read_resource(
        "mcp://hostname/user/testuser/profile"
    )
    print(f"✅ Received resource for profile response:\n  {profile_content}")

    print("\n========================================")
    print("➡️ Reading user document template resource...")
    print("========================================")
    doc_content = await session.read_resource(
        "mcp://hostname/user/testuser/document/123"
    )
    print(f"✅ Received resource for document response:\n  {doc_content}")
    print("========================================")

  except mcp.McpError as e:
    print(f"An error occurred: {e}")
  finally:
    await session.close()


def main(argv) -> None:
  if len(argv) > 2:
    raise app.UsageError("Too many command-line arguments.")

  asyncio.run(call_server(host=_SERVER_HOST.value, port=_SERVER_PORT.value))


if __name__ == "__main__":
  app.run(main)
