"""Defines the abstract base class for client sessions.

This is a placeholder Abstract class which will most likely be replaced by a 
new BaseClientSession class in the MCP package, depending on how our 
abstractions proposal (https://github.com/sreenithi/mcp-python-sdk/pull/1) 
is accepted.
"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from mcp import types as mcp_types
import pydantic


class ClientTransportSession(ABC):
  """Abstract base class for client sessions."""

  @abstractmethod
  async def initialize(self) -> mcp_types.InitializeResult:
    """Send an initialize request."""
    raise NotImplementedError

  @abstractmethod
  async def send_ping(self) -> mcp_types.EmptyResult:
    """Send a ping request."""
    raise NotImplementedError

  @abstractmethod
  async def list_resources(self) -> mcp_types.ListResourcesResult:
    """Send a resources/list request."""
    raise NotImplementedError

  @abstractmethod
  async def list_resource_templates(
      self,
  ) -> mcp_types.ListResourceTemplatesResult:
    """Send a resources/templates/list request."""
    raise NotImplementedError

  @abstractmethod
  async def read_resource(
      self, uri: pydantic.AnyUrl
  ) -> mcp_types.ReadResourceResult:
    """Send a resources/read request."""
    raise NotImplementedError

  @abstractmethod
  async def subscribe_resource(
      self, uri: pydantic.AnyUrl
  ) -> mcp_types.EmptyResult:
    """Send a resources/subscribe request."""
    raise NotImplementedError

  @abstractmethod
  async def unsubscribe_resource(
      self, uri: pydantic.AnyUrl
  ) -> mcp_types.EmptyResult:
    """Send a resources/unsubscribe request."""
    raise NotImplementedError

  @abstractmethod
  async def call_tool(
      self,
      name: str,
      arguments: Any | None = None,
      read_timeout_seconds: timedelta | None = None,
  ) -> mcp_types.CallToolResult:
    """Send a tools/call request."""
    raise NotImplementedError

  @abstractmethod
  async def list_prompts(self) -> mcp_types.ListPromptsResult:
    """Send a prompts/list request."""
    raise NotImplementedError

  @abstractmethod
  async def get_prompt(
      self,
      name: str,
      arguments: dict[str, str] | None = None,
  ) -> mcp_types.GetPromptResult:
    """Send a prompts/get request."""
    raise NotImplementedError

  @abstractmethod
  async def list_tools(self) -> mcp_types.ListToolsResult:
    """Send a tools/list request."""
    raise NotImplementedError

  @abstractmethod
  async def send_roots_list_changed(self) -> None:
    """Send a roots/list_changed notification."""
    raise NotImplementedError
