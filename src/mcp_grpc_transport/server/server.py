"""Server for MCP gRPC transport."""

import logging
from typing import Any, Literal

import anyio
from grpc import aio
from mcp.server import fastmcp
from mcp.types import Icon
from mcp_grpc_transport.server import grpc_server
import pydantic_settings

logger = logging.getLogger(__name__)


class GrpcTransportSettings(pydantic_settings.BaseSettings):
  """Settings for the gRPC transport server."""

  # TODO(asheshvidyut): Implement proper type hints for gRPC settings.
  # TODO(ssreenithi): Add other settings from mcp_grpc as needed.
  grpc_enable_reflection: bool = False


class FastMCPGrpc(fastmcp.FastMCP):
  """FastMCP gRPC server."""

  def __init__(
      self,
      target: str,
      name: str | None = None,
      instructions: str | None = None,
      website_url: str | None = None,
      icons: list[Icon] | None = None,
      retry_interval: int | None = None,
      grpc_settings: GrpcTransportSettings | None = None,
      **kwargs: Any,
  ):
    super().__init__(
        name=name,
        instructions=instructions,
        website_url=website_url,
        icons=icons,
        retry_interval=retry_interval,
        **kwargs,
    )

    self.grpc_settings: GrpcTransportSettings | None = grpc_settings
    self.target = target

    self._grpc_server: aio.Server | None = None

  def run(
      self,
      transport: Literal["stdio", "sse", "streamable-http", "grpc"] = "grpc",
      mount_path: str | None = None,
  ):
    """Run the gRPC MCP server. Note this is a synchronous function.

    Args:
      transport: Transport protocol to use. 'gRPC' is the only accepted value
        and other values ("stdio", "sse", "streamable-http") will raise a
        ValueError.
      mount_path: Optional mount path for SSE transport. Argument is included 
        just for compatibility with the parent FastMCP class. However, this is
        not required for gRPC transport and will be ignored.
    """

    if transport != "grpc":
      raise ValueError("This server only supports gRPC transport.")

    if mount_path:
      logger.warning(
          "Ignoring provided value for mount_path, as it is not required for "
          "gRPC transport."
      )

    # Use a wrapper to avoid pytype wrong-arg-types error with anyio.run.
    async def runner(*unused_args: Any) -> None:
      await self.run_grpc_async()

    anyio.run(runner)

  async def run_grpc_async(self) -> None:
    """Run the MCP server with gRPC transport."""

    self._grpc_server = await grpc_server.create_mcp_grpc_server(
        mcp_grpc_server=self,
    )
    try:
      await self._grpc_server.wait_for_termination()
    finally:
      await self.stop_grpc_server(1)

  async def stop_grpc_server(self, grace_time: float = 1.0) -> None:
    """Stop the MCP gRPC server.

    This function is mainly intended for use in tests to explicitly stop the
    server. In real world scenarios, the server will be gracefully stopped
    when the server process terminates.

    Args:
      grace_time: The grace time in seconds to wait for the server to stop.
      This is the amount of time to wait for pending RPCs to complete before
       forcefully stopping the server.
    """
    if self._grpc_server:
      await self._grpc_server.stop(grace_time)
      self._grpc_server = None

  def add_to_existing_server(self, server: aio.Server):
    """Attach the FastMCP server with an existing gRPC server.

    Args:
      server: The existing gRPC server to attach the MCP server to.
    """
    grpc_server.attach_mcp_server_to_grpc_server(self, server)

  # -----------------------------------------------------------------------
  # Some Unsupported Methods from FastMCP related to other transports.
  # While only the below methods are explicitly marked as unsupported, there
  # could be others that are not supported as well. These are inherited from the
  # parent class FastMCP, but are not required when using the gRPC transport.
  # -----------------------------------------------------------------------

  async def run_stdio_async(self, *args, **kwargs) -> None:
    raise NotImplementedError("This class only supports gRPC transport.")

  async def run_sse_async(self, *args, **kwargs) -> None:
    raise NotImplementedError("This class only supports gRPC transport.")

  async def run_streamable_http_async(self, *args, **kwargs) -> None:
    raise NotImplementedError("This class only supports gRPC transport.")

  async def sse_app(self, *args, **kwargs):  # pytype: disable=signature-mismatch
    raise NotImplementedError("This class only supports gRPC transport.")

  async def streamable_http_app(self, *args, **kwargs):  # pytype: disable=signature-mismatch
    raise NotImplementedError("This class only supports gRPC transport.")

  async def custom_route(self, *args, **kwargs):  # pytype: disable=signature-mismatch
    raise NotImplementedError("This class only supports gRPC transport.")
