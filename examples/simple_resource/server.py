"""Example MCP server with gRPC transport for simple resource and resource templates."""

import asyncio
from absl import app
from absl import flags
from absl import logging
from mcp.server import fastmcp
from mcp_grpc_transport.server.grpc_server import GRPCTransportSettings, serve_grpc

_PORT = flags.DEFINE_integer("port", 50052, "Server port")


def setup_server() -> fastmcp.FastMCP:
  """Set up the FastMCP server with resource and resource templates."""
  mcp = fastmcp.FastMCP(
      name="Simple Resource gRPC Server",
      instructions=(
          "A simple MCP server demonstrating gRPC transport with a simple"
          " resource."
      ),
  )

  @mcp.resource("mcp://resource/simple", mime_type="text/plain")
  def simple_resource() -> str:
    """A simple resource that returns text."""
    return "Hello from resource!"

  @mcp.resource("mcp://hostname/user/{user}/profile")
  def user_profile_resource(user: str) -> str:
    """A templated resource for user profiles."""
    return f"Profile for {user}"

  @mcp.resource("mcp://hostname/user/{user}/document/{doc_id}")
  def user_document_resource(user: str, doc_id: str) -> str:
    """A templated resource for user documents."""
    return f"Document {doc_id} for {user}"

  return mcp


def main(argv) -> None:
  if len(argv) > 1:
    raise app.UsageError("Too many command-line arguments.")

  mcp = setup_server()
  logging.info("Starting MCP gRPC Server on port %s...", _PORT.value)
  logging.info("Server will be available on localhost:%s", _PORT.value)
  logging.info("Press Ctrl-C to stop the server")

  try:
    settings = GRPCTransportSettings(enable_reflection=True)
    asyncio.run(serve_grpc(mcp, f"127.0.0.1:{_PORT.value}", settings))
  except KeyboardInterrupt:
    logging.info("Server stopped by user")
  except Exception as e:
    logging.error("Server error: %s", e)
    raise


if __name__ == "__main__":
  app.run(main)
