"""Defines the session object for gRPC tool calls."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any
import uuid

import grpc
from mcp.client.session import (
    ElicitationFnT,
    ListRootsFnT,
    LoggingFnT,
    MessageHandlerFnT,
    SamplingFnT,
)

import mcp.shared.exceptions as mcp_exceptions
import mcp.types as mcp_types
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.utils import convert_types
from mcp_grpc_transport.utils import version_utils
import pydantic

from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc

logger = logging.getLogger(__name__)


@dataclass
class GRPCClientTransportSettings:
  """The settings used to connect to the gRPC server."""

  interceptors: Sequence[Any] | None = None
  options: Sequence[tuple[str, Any]] | None = None
  compression: grpc.Compression | None = None
  channel_credentials: grpc.ChannelCredentials | None = None


class GRPCClientSession(mcp_grpc_client.ClientTransportSession):
  """A session object for gRPC tool calls that uses a queue."""

  def __init__(
      self,
      target: str,
      read_timeout_seconds: timedelta | None = None,
      sampling_callback: SamplingFnT | None = None,
      elicitation_callback: ElicitationFnT | None = None,
      list_roots_callback: ListRootsFnT | None = None,
      logging_callback: LoggingFnT | None = None,
      message_handler: MessageHandlerFnT | None = None,
      client_info: mcp_types.Implementation | None = None,
      *,
      grpc_settings: GRPCClientTransportSettings | None = None,
  ):
    self.target = target
    self.grpc_settings = (
        grpc_settings if grpc_settings is not None
        else GRPCClientTransportSettings()
    )

    self._sampling_callback = sampling_callback
    self._elicitation_callback = elicitation_callback
    self._list_roots_callback = list_roots_callback
    self._logging_callback = logging_callback
    self._message_handler = message_handler
    self._client_info = client_info

    if self.grpc_settings.channel_credentials is not None:
      self.channel = grpc.aio.secure_channel(
          target,
          self.grpc_settings.channel_credentials,
          options=self.grpc_settings.options,
          compression=self.grpc_settings.compression,
          interceptors=self.grpc_settings.interceptors,
      )
    else:
      self.channel = grpc.aio.insecure_channel(
          target,
          options=self.grpc_settings.options,
          compression=self.grpc_settings.compression,
          interceptors=self.grpc_settings.interceptors,
      )

    self.stub = mcp_pb2_grpc.McpStub(self.channel)

    self.negotiated_version = version_utils.LATEST_PROTOCOL_VERSION

    self._ongoing_requests: set[str] = set()

    # TODO(ssreenithi): Add cache support with ttl instead of this placeholder.
    self.ttl = read_timeout_seconds

  def __repr__(self) -> str:
    return (
        f"GRPCClientSession(target='{self.target!r}',"
        f" grpc_settings={self.grpc_settings})"
    )

  async def __aenter__(self):
    """Context management enter."""
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb):
    """Context management exit. Closes the gRPC channel."""
    await self.close()

  def get_version_metadata(self) -> list[tuple[str, str]]:
    """Gets the version metadata to be sent with the gRPC request."""
    return [
        (
            version_utils.MCP_PROTOCOL_VERSION_KEY,
            self.negotiated_version,
        )
    ]

  def _check_and_update_version(self, rpc_error: grpc.aio.AioRpcError) -> bool:
    """Checks if the version is supported and updates the version metadata."""
    if rpc_error.code() is grpc.StatusCode.UNIMPLEMENTED:
      initial_metadata = rpc_error.initial_metadata()
      negotiated_version = version_utils.get_metadata_value(
          initial_metadata, version_utils.MCP_PROTOCOL_VERSION_KEY
      )

      if (
          negotiated_version is not None
          and negotiated_version in version_utils.SUPPORTED_PROTOCOL_VERSIONS
      ):
        logger.info(
            "Server returned protocol version %s in initial metadata."
            " Negotiating to this version. Retrying.",
            negotiated_version,
        )
        self.negotiated_version = negotiated_version
        return True

    return False

  async def _call_unary_rpc_with_version_negotiation(
      self, rpc_method: Any, request: Any, timeout: float | None = None,
      metadata: list[tuple[str, str]] | None = None
  ) -> Any:
    """Calls a unary gRPC method with retry logic for version mismatch.

    Args:
      rpc_method: The gRPC method to call.
      request: The request to send.
      timeout: The timeout for the RPC.
      metadata: The metadata to send with the RPC.

    Returns:
      The response from the RPC.

    Raises:
      grpc.aio.AioRpcError: If the RPC fails for reasons other than
      version mismatch.
    """

    if metadata is None:
      metadata = []

    try:
      response = await rpc_method(
          request,
          metadata=(metadata + self.get_version_metadata()),
          timeout=timeout,
      )
      return response

    except grpc.aio.AioRpcError as rpc_error:
      if self._check_and_update_version(rpc_error):
        response = await rpc_method(
            request,
            metadata=(metadata + self.get_version_metadata()),
            timeout=timeout,
        )
        return response

      # If version negotiation fails or RPC failed for a different error,
      # re-raise the original error.
      raise

  async def close(self) -> None:
    """Closes the channel."""
    await self.channel.close()

  async def list_tools(self) -> mcp_types.ListToolsResult:
    """Sends a tools/list request."""
    list_tools_request_proto = mcp_messages_pb2.ListToolsRequest()
    try:
      list_tools_response_proto = (
          await self._call_unary_rpc_with_version_negotiation(
              self.stub.ListTools, list_tools_request_proto,
          )
      )

      return convert_types.list_tools_result_from_proto(
          list_tools_response_proto
      )

    except Exception as e:
      logger.error("Error during ListTools.", exc_info=True)
      mcp_error = convert_types.convert_exception_to_mcp_error(
          e, "Error during ListTools"
      )
      raise mcp_error from e

  async def call_tool(
      self,
      name: str,
      arguments: dict[str, Any] | None = None,
      read_timeout_seconds: timedelta | None = None,
  ) -> mcp_types.CallToolResult:
    """Sends a tools/call request."""

    request_id = str(uuid.uuid4())
    self._ongoing_requests.add(request_id)

    request_params = mcp_types.CallToolRequestParams(
        name=name,
        arguments=arguments,
    )
    request_proto = convert_types.call_tool_params_to_proto(request_params)
    try:
      timeout = (
          read_timeout_seconds.total_seconds() if read_timeout_seconds else None
      )

      response = await self._call_unary_rpc_with_version_negotiation(
          self.stub.CallTool, request_proto, timeout=timeout,
      )

      return convert_types.call_tool_result_from_proto(response)

    except Exception as e:
      logger.exception("Error during CallTool for tool: %s", name)
      mcp_error = convert_types.convert_exception_to_mcp_error(
          e, "Error during CallTool"
      )
      raise mcp_error from e

    finally:
      self._ongoing_requests.discard(request_id)

  async def list_resources(self) -> mcp_types.ListResourcesResult:
    """Sends a resources/list request."""
    list_resources_request_proto = mcp_messages_pb2.ListResourcesRequest()
    try:
      list_resources_response_proto = (
          await self._call_unary_rpc_with_version_negotiation(
              self.stub.ListResources, list_resources_request_proto,
          )
      )
      return convert_types.list_resources_result_from_proto(
          list_resources_response_proto
      )
    except Exception as e:
      logger.exception("Error during ListResources.")
      raise convert_types.convert_exception_to_mcp_error(
          e, "Error during ListResources"
      ) from e

  async def list_resource_templates(
      self
  ) -> mcp_types.ListResourceTemplatesResult:
    """Sends a resources/templates/list request."""
    list_resource_templates_request_proto = (
        mcp_messages_pb2.ListResourceTemplatesRequest()
    )
    try:
      list_resource_templates_response_proto = (
          await self._call_unary_rpc_with_version_negotiation(
              self.stub.ListResourceTemplates,
              list_resource_templates_request_proto,
          )
      )
      return convert_types.list_resource_templates_result_from_proto(
          list_resource_templates_response_proto
      )
    except Exception as e:
      logger.exception("Error during ListResourceTemplates.")
      raise convert_types.convert_exception_to_mcp_error(
          e, "Error during ListResourceTemplates"
      ) from e

  async def read_resource(
      self, uri: pydantic.AnyUrl
  ) -> mcp_types.ReadResourceResult:
    """Sends a resources/read request."""
    read_resource_request_proto = (
        convert_types.read_resource_request_params_to_proto(
            mcp_types.ReadResourceRequestParams(uri=uri)
        )
    )
    try:
      read_resource_response_proto = (
          await self._call_unary_rpc_with_version_negotiation(
              self.stub.ReadResource,
              read_resource_request_proto,
          )
      )
      return convert_types.read_resource_result_from_proto(
          read_resource_response_proto
      )
    except Exception as e:
      logger.exception("Error during ReadResource for uri: %s", uri)
      raise convert_types.convert_exception_to_mcp_error(
          e, f"Error during ReadResource for uri: {uri}"
      ) from e

  #####################################################################
  # TODO(ssreenithi): Check and add support for the following methods
  # as necessary
  #####################################################################

  async def initialize(self) -> mcp_types.InitializeResult:
    """Send an initialize request."""
    raise NotImplementedError

  async def send_ping(self) -> mcp_types.EmptyResult:
    """Send a ping request."""
    raise NotImplementedError

  async def subscribe_resource(
      self, uri: pydantic.AnyUrl
  ) -> mcp_types.EmptyResult:
    """Send a resources/subscribe request."""
    raise NotImplementedError

  async def unsubscribe_resource(
      self, uri: pydantic.AnyUrl
  ) -> mcp_types.EmptyResult:
    """Send a resources/unsubscribe request."""
    raise NotImplementedError

  async def list_prompts(self) -> mcp_types.ListPromptsResult:
    """Send a prompts/list request."""
    raise NotImplementedError

  async def get_prompt(
      self, name: str, arguments: dict[str, str] | None = None
  ) -> mcp_types.GetPromptResult:
    """Send a prompts/get request."""
    raise NotImplementedError

  async def send_roots_list_changed(self) -> None:
    """Send a roots/list_changed notification."""
    raise NotImplementedError
