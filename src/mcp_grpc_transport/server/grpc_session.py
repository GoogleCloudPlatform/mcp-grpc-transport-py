"""Defines the session object for gRPC tool calls."""

import logging
from typing import Any

import mcp
import mcp.types as mcp_types
import pydantic

logger = logging.getLogger(__name__)


# TODO(ssreenithi): Inherit from ServerTransportSession once available
class GRPCSession(mcp.ServerSession):
  """A session object for gRPC tool calls."""

  def __init__(self):
    pass

  async def send_log_message(
      self,
      level: mcp_types.LoggingLevel,
      data: Any,
      logger: str | None = None,
      related_request_id: mcp_types.RequestId | None = None,
  ) -> None:
    """Logs tool messages to the server console."""
    raise NotImplementedError

  async def send_resource_updated(self, uri: pydantic.AnyUrl) -> None:
    """Send a resource updated notification."""
    raise NotImplementedError

  async def list_roots(self) -> mcp_types.ListRootsResult:
    """Send a roots/list request."""
    raise NotImplementedError

  async def elicit(
      self,
      message: str,
      requestedSchema: mcp_types.ElicitRequestedSchema,
      related_request_id: mcp_types.RequestId | None = None,
  ) -> mcp_types.ElicitResult:
    """Send an elicitation/create request."""
    raise NotImplementedError

  async def send_ping(self) -> mcp_types.EmptyResult:
    """This is not needed for gRPC."""
    raise NotImplementedError

  async def send_progress_notification(
      self,
      progress_token: str | int,
      progress: float,
      total: float | None = None,
      message: str | None = None,
      related_request_id: mcp_types.RequestId | None = None,
  ) -> None:
    """Puts a progress notification onto the response queue for a request that is currently being processed."""
    raise NotImplementedError

  async def send_resource_list_changed(self) -> None:
    """This is not needed for gRPC, as we rely on TTL."""
    raise NotImplementedError

  async def send_tool_list_changed(self) -> None:
    """This is not needed for gRPC, as we rely on TTL."""
    raise NotImplementedError

  async def send_prompt_list_changed(self) -> None:
    """This is not needed for gRPC, as we rely on TTL."""
    raise NotImplementedError
