"""Example MCP server with gRPC transport for a simple tool."""

import asyncio
from absl import app
from absl import flags
from absl import logging
from mcp.server import fastmcp
from mcp_grpc_transport.server.grpc_server import GRPCTransportSettings, serve_grpc

_PORT = flags.DEFINE_integer("port", 50051, "Server port")


def setup_server() -> fastmcp.FastMCP:
  """Set up the FastMCP server with simple tool."""
  mcp = fastmcp.FastMCP(
      name="Simple Tool gRPC Server",
      instructions=(
          "A simple MCP server demonstrating gRPC transport with a simple tool."
      ),
  )

  @mcp.tool()
  def greeting_tool(name: str) -> str:
    """A simple tool that returns a greeting."""
    greeting = f"Hello, {name}!"
    logging.info("Greeting %s", name)
    return greeting

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
