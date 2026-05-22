"""Tests for server creation."""

import time

import anyio
from grpc import aio
from mcp.server.fastmcp import FastMCP
from mcp_grpc_transport.server import grpc_server
from tests import test_utils


def test_server_creation_and_run():
  """Tests if the FastMCP server can be served via gRPC."""
  port = test_utils.find_free_port()
  target = f'localhost:{port}'

  fastmcp_server = FastMCP(
      name='test-server',
  )

  server = None
  try:
    server = grpc_server.create_mcp_grpc_server(fastmcp_server, target)

    time.sleep(0.2)

  finally:
    if server is not None:
      anyio.run(grpc_server.stop_grpc_server, server, 0.5)


def test_attach_mcp_server_to_grpc_server():
  """Tests if attach_mcp_server_to_grpc_server attaches servicer."""
  port = test_utils.find_free_port()
  target = f'localhost:{port}'
  fastmcp_server = FastMCP(name='test-server')
  server = aio.server()

  grpc_server.attach_mcp_server_to_grpc_server(
      fastmcp_server, server
  )
  server.add_insecure_port(target)

  async def _run():
    try:
      await server.start()
      await anyio.sleep(0.2)
    finally:
      await server.stop(0.5)

  anyio.run(_run)
