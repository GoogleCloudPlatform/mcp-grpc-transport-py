"""gRPC server transport for MCP.

This module provides a gRPC transport for MCP servers.
"""

import logging
from typing import TYPE_CHECKING

import grpc
from grpc import aio

from mcp_grpc_transport_proto import mcp_pb2_grpc

if TYPE_CHECKING:
  from mcp_grpc_transport.server import FastMCPGrpc

logger = logging.getLogger(__name__)


# TODO(ssreenithi): Uncomment and update Servicer methods with new context.
class McpServicer(mcp_pb2_grpc.McpServicer):
  """gRPC servicer for MCP protocol.

  This servicer will contain all the handlers required by gRPC servers to handle
  MCP requests related to tools, resources, prompts, etc.
  """

  def __init__(self, mcp_server: "FastMCPGrpc"):
    self.mcp_grpc_server: "FastMCPGrpc" = mcp_server


def attach_mcp_server_to_grpc_server(
    mcp_grpc_server: "FastMCPGrpc",
    server: grpc.aio.Server,
) -> None:
  """Attach a MCP server to a gRPC server.

  Args:
      mcp_grpc_server: The MCP server instance to handle requests.
      server: The gRPC server instance to attach the MCP server to.
  """
  # Create servicer and add to server
  servicer = McpServicer(mcp_grpc_server)
  mcp_pb2_grpc.add_McpServicer_to_server(servicer, server)  # type: ignore


async def create_mcp_grpc_server(
    mcp_grpc_server: "FastMCPGrpc",
) -> aio.Server:
  """Create a simple gRPC server for MCP at the set target address.

  Args:
      mcp_grpc_server: The MCP server instance to handle requests

  Returns:
      Configured gRPC server ready to serve
  """

  target = mcp_grpc_server.target

  server = aio.server()

  attach_mcp_server_to_grpc_server(mcp_grpc_server, server)

  # Configure server port
  server.add_insecure_port(target)

  # Start gRPC server
  await server.start()
  logger.info("gRPC server started on %s", target)
  return server
