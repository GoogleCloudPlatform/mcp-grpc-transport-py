"""gRPC server transport for MCP.

This module provides a gRPC transport for MCP servers.
"""

from concurrent.futures import Executor
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from typing import Any, Sequence, TYPE_CHECKING

import grpc
from grpc import aio
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.lowlevel import server as mcp_server
import mcp_grpc_transport.server as mcp_grpc_transport_server
from mcp_grpc_transport.utils import convert_types
from mcp_grpc_transport.utils import version_utils

from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc


if TYPE_CHECKING:
  from mcp.server import FastMCP

logger = logging.getLogger(__name__)


@dataclass
class GRPCTransportSettings():
  """Settings for the gRPC transport server."""

  enable_reflection: bool = False
  migration_thread_pool: Executor | None = None
  handlers: Sequence[grpc.GenericRpcHandler] | None = None
  interceptors: Sequence[Any] | None = None
  options: Sequence[tuple[str, Any]] | None = None
  maximum_concurrent_rpcs: int | None = None
  compression: grpc.Compression | None = None
  credentials: grpc.ServerCredentials | None = None


class McpServicer(mcp_pb2_grpc.McpServicer):
  """gRPC servicer for MCP protocol.

  This servicer will contain all the handlers required by gRPC servers to handle
  MCP requests related to tools, resources, prompts, etc.
  """

  def __init__(self, fastmcp_server: "FastMCP"):
    self.fastmcp_server: "FastMCP" = fastmcp_server

  async def CallTool(
      self,
      request: mcp_messages_pb2.CallToolRequest,
      context: grpc.aio.ServicerContext,
  ):
    # Verify the protocol version from the metadata and abort the RPC if it is
    # not supported, while sending the initial metadata with the server's
    # supported latest version.
    await version_utils.verify_protocol_version_from_metadata(context)

    # Run mcp.call_tool under the gRPC request context.
    with grpc_request_context(request) as (_, _):
      try:
        # Validate the CallToolRequest before calling the tool.
        convert_types.validate_call_tool_request_proto(request)

        call_tool_params = convert_types.call_tool_params_from_proto(
            request
        )

        response = await self.fastmcp_server.call_tool(
            call_tool_params.name, call_tool_params.arguments
        )

        # The result object from FastMCP.call_tool to convert, can be either of -
        #   - a mcp_types.CallToolResult object.
        #   or other types for backward compatibility like:
        #   - unstructured content (Sequence[mcp_types.ContentBlock]),
        #   - structured content (dict[str, Any]),
        #   - a tuple of both the above.
        #
        # Hence unify and convert it into a standard CallToolResult object,
        # for easier conversion to proto response.
        call_tool_result = convert_types.unify_call_tool_result(response)

        return convert_types.call_tool_result_to_proto(call_tool_result)

      except ToolError as e:
        logger.error("Error during tool call: %s", e, exc_info=True)
        return convert_types.call_tool_result_to_proto(
            convert_types.tool_error_to_call_tool_result(e)
        )

      except Exception as e:  # pylint: disable=broad-except
        logger.error("Error during tool call: %s", e, exc_info=True)
        # For other exceptions, return a CallToolResponse with is_error=True
        return convert_types.call_tool_result_to_proto(
            convert_types.tool_error_to_call_tool_result(
                ToolError(f"Error during tool call: {e!r}")
            )
        )

  async def ListTools(
      self,
      request: mcp_messages_pb2.ListToolsRequest,
      context: grpc.aio.ServicerContext,
  ):
    # Verify the protocol version from the metadata and abort the RPC if it is
    # not supported, while sending the initial metadata with the server's
    # supported latest version.
    await version_utils.verify_protocol_version_from_metadata(context)

    try:
      # Run mcp.list_tools under the gRPC request context.
      with grpc_request_context(request):
        tools = await self.fastmcp_server.list_tools()

      proto_tools = [convert_types.tool_to_proto(tool) for tool in tools]

      return mcp_messages_pb2.ListToolsResponse(tools=proto_tools)

    except Exception as e:  # pylint: disable=broad-except
      logger.exception("Error during ListTools call. %r", e)
      await context.abort(
          grpc.StatusCode.INTERNAL, f"Error during ListTools call. {e!r}"
      )

  async def ListResources(
      self,
      request: mcp_messages_pb2.ListResourcesRequest,
      context: grpc.aio.ServicerContext,
  ):

    # Verify the protocol version from the metadata and abort the RPC if it is
    # not supported, while sending the initial metadata with the server's
    # supported latest version.
    await version_utils.verify_protocol_version_from_metadata(context)

    try:
      # Run mcp.list_resources under the gRPC request context.
      with grpc_request_context(request):
        resources = await self.fastmcp_server.list_resources()

        return mcp_messages_pb2.ListResourcesResponse(resources=[
            convert_types.resource_to_proto(resource) for resource in resources
        ])

    except Exception as e:  # pylint: disable=broad-except
      logger.exception("Error during ListResources call.")
      await context.abort(
          grpc.StatusCode.INTERNAL, f"Error during ListResources call. {e!r}"
      )

  async def ListResourceTemplates(
      self,
      request: mcp_messages_pb2.ListResourceTemplatesRequest,
      context: grpc.aio.ServicerContext,
  ):
    # Verify the protocol version from the metadata and abort the RPC if it is
    # not supported, while sending the initial metadata with the server's
    # supported latest version.
    await version_utils.verify_protocol_version_from_metadata(context)

    try:
      # Run mcp.list_resource_templates under the gRPC request context.
      with grpc_request_context(request):
        resource_templates = await self.fastmcp_server.list_resource_templates()

        return mcp_messages_pb2.ListResourceTemplatesResponse(
            resource_templates=[
                convert_types.resource_template_to_proto(resource_template)
                for resource_template in resource_templates
            ]
        )

    except Exception as e:  # pylint: disable=broad-except
      logger.exception("Error during ListResourceTemplates call.")
      await context.abort(
          grpc.StatusCode.INTERNAL,
          f"Error during ListResourceTemplates call. {e!r}"
      )

  async def ReadResource(
      self,
      request: mcp_messages_pb2.ReadResourceRequest,
      context: grpc.aio.ServicerContext,
  ):
    """Read a resource.

    The size of the resource is limited by the max_receive_message_length
    channel option of gRPC client, which is 4MB by default in OSS gRPC Python.
    This can be increased by setting the channel option:
    ("grpc.max_receive_message_length", <size_in_bytes>).

    Args:
        request: The ReadResourceRequest proto to send to the RPC.
        context: The gRPC servicer context.

    Returns:
        The ReadResourceResponse proto.
    """
    # Verify the protocol version from the metadata and abort the RPC if it is
    # not supported, while sending the initial metadata with the server's
    # supported latest version.
    await version_utils.verify_protocol_version_from_metadata(context)

    try:
      # Run mcp.read_resource under the gRPC request context.
      with grpc_request_context(request):
        params = convert_types.read_resource_request_params_from_proto(request)
        contents = await self.fastmcp_server.read_resource(params.uri)
        return mcp_messages_pb2.ReadResourceResponse(
            resource=[
                convert_types.resource_contents_to_proto(params.uri, content)
                for content in contents
            ]
        )

    except ValueError as e:
      logger.exception("Error during ReadResource call.")
      await context.abort(
          grpc.StatusCode.NOT_FOUND, f"Error during ReadResource call. {e!r}"
      )

    except Exception as e:  # pylint: disable=broad-except
      logger.exception("Error during ReadResource call.")
      await context.abort(
          grpc.StatusCode.INTERNAL, f"Error during ReadResource call. {e!r}"
      )


@contextmanager
def grpc_request_context(request: Any):
  """Sets RequestContext for the duration of a gRPC request."""

  session = mcp_grpc_transport_server.GRPCSession()

  grpc_req_ctx = mcp_grpc_transport_server.GRPCRequestContext.from_grpc(
      request=request,
      session=session,
  )
  token = mcp_server.request_ctx.set(grpc_req_ctx)

  try:
    yield token, session
  finally:
    mcp_server.request_ctx.reset(token)


def attach_mcp_server_to_grpc_server(
    fastmcp_server: "FastMCP",
    server: grpc.aio.Server,
) -> None:
  """Attach a MCP server to a gRPC server.

  Args:
      fastmcp_server: The MCP server instance to handle requests.
      server: The gRPC server instance to attach the MCP server to.
  """
  # Create servicer and add to server
  servicer = McpServicer(fastmcp_server)
  mcp_pb2_grpc.add_McpServicer_to_server(servicer, server)  # type: ignore


async def create_mcp_grpc_server(
    fastmcp_server: "FastMCP",
    target: str,
    grpc_settings: GRPCTransportSettings | None = None,
) -> aio.Server:
  """Create a simple gRPC server for MCP at the set target address.

  Args:
      fastmcp_server: The MCP server instance to handle requests.
      target: The target address for the gRPC server.
      grpc_settings: The gRPC transport settings to use for the server.

  Returns:
      Configured gRPC server ready to serve
  """

  if grpc_settings is None:
    grpc_settings = GRPCTransportSettings()

  server = aio.server(
      migration_thread_pool=grpc_settings.migration_thread_pool,
      handlers=grpc_settings.handlers,
      interceptors=grpc_settings.interceptors,
      options=grpc_settings.options,
      maximum_concurrent_rpcs=grpc_settings.maximum_concurrent_rpcs,
      compression=grpc_settings.compression,
  )

  attach_mcp_server_to_grpc_server(fastmcp_server, server)

  # Configure server port
  if grpc_settings.credentials:
    server.add_secure_port(target, grpc_settings.credentials)
  else:
    server.add_insecure_port(target)

  # Start gRPC server
  await server.start()
  logger.info("gRPC server started on %s", target)
  return server


async def serve_grpc(
    fastmcp_server: "FastMCP",
    target: str,
    grpc_settings: GRPCTransportSettings | None = None,
) -> None:
  """Creates and runs a simple gRPC server for MCP at the set target address.

  Args:
      fastmcp_server: The MCP server instance to handle requests.
      target: The target address for the gRPC server.
      grpc_settings: The gRPC transport settings to use for the server.


  """
  server = await create_mcp_grpc_server(fastmcp_server, target, grpc_settings)

  try:
    await server.wait_for_termination()
  finally:
    await stop_grpc_server(server, 1)


async def stop_grpc_server(server: aio.Server, grace_time: float = 1.0) -> None:
  """Stop the MCP gRPC server.

  This function is mainly intended for use in tests to explicitly stop the
  server. In real world scenarios, the server will be gracefully stopped
  when the server process terminates.

  Args:
      server: The gRPC server instance to stop.
      grace_time: The grace time in seconds to wait for the server to stop.
      This is the amount of time to wait for pending RPCs to complete before
      forcefully stopping the server.
  """
  await server.stop(grace_time)
