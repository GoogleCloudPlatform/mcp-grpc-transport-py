"""Utility functions to convert between MCP and Protobuf types."""

import base64
import logging
from typing import Any, Sequence

from google.protobuf import json_format
from mcp import types as mcp_types
from mcp.server.fastmcp.exceptions import ToolError
from mcp_grpc_transport.server import grpc_session

from google.protobuf import struct_pb2
from mcp_grpc_transport_proto import mcp_pb2

logger = logging.getLogger(__name__)

###################### ListTools helper functions ##########################


def tool_to_proto(tool: mcp_types.Tool) -> mcp_pb2.Tool:
  """Converts a MCP Tool type to a Protobuf Tool message.

  Args:
      tool: The MCP Tool type to convert.

  Returns:
      The converted Protobuf Tool message.
  """

  try:
    input_schema_dict = tool.inputSchema
    input_schema = json_format.ParseDict(input_schema_dict, struct_pb2.Struct())
  except json_format.ParseError as e:
    logger.error("Failed to parse inputSchema for tool %s: %s", tool.name, e)
    raise

  try:
    output_schema = None
    if tool.outputSchema is not None:
      output_schema = json_format.ParseDict(
          tool.outputSchema, struct_pb2.Struct()
      )
  except json_format.ParseError as e:
    logger.error("Failed to parse outputSchema for tool %s: %s", tool.name, e)
    raise

  return mcp_pb2.Tool(
      name=tool.name,
      title=tool.title,
      description=tool.description,
      input_schema=input_schema,
      output_schema=output_schema,
  )

################### End of ListTools helper functions ######################


################### CallTool request helper functions ######################


def get_call_tool_params_from_proto(
    request: mcp_pb2.CallToolRequest,
) -> mcp_types.CallToolRequestParams:
  """Extracts CallToolRequestParams from a CallToolRequest proto message.

  Args:
      request: The CallToolRequest proto message to extract from.

  Returns:
      The extracted CallToolRequestParams object.
  """

  arguments = None
  if request.request.HasField("arguments"):
    arguments = json_format.MessageToDict(request.request.arguments)

  return mcp_types.CallToolRequestParams(
      name=request.request.name,
      arguments=arguments,
  )


def validate_call_tool_request_proto(
    request: mcp_pb2.CallToolRequest,
) -> None:
  """Validates the CallToolRequest proto message.

  Args:
      request: The CallToolRequest to validate.

  Raises:
      ValueError: If the request is invalid (e.g. empty request field or
        empty tool name).
  """

  if not request.HasField("request"):
    raise ValueError("Request field cannot be empty.")

  tool_name = request.request.name

  if not tool_name:
    raise ValueError("Tool name cannot be empty.")


################# End of CallTool request helper functions ################

################### CallTool response helper functions ####################


def _content_block_to_proto(
    content_block: mcp_types.ContentBlock,
) -> mcp_pb2.CallToolResponse.Content | None:
  """Converts a MCP type ContentBlock to a CallToolResponse.Content Proto message.

  Args:
      content_block: The mcp.types.ContentBlock object to convert.

  Returns:
      The converted CallToolResponse.Content Protobuf message or None if the
      content block is not a valid content block.
  """

  if isinstance(content_block, mcp_types.TextContent):
    return mcp_pb2.CallToolResponse.Content(
        text=mcp_pb2.TextContent(text=content_block.text)
    )

  elif isinstance(content_block, mcp_types.ImageContent):
    return mcp_pb2.CallToolResponse.Content(
        image=mcp_pb2.ImageContent(
            data=base64.b64decode(content_block.data),
            mime_type=content_block.mimeType,
        )
    )

  elif isinstance(content_block, mcp_types.AudioContent):
    return mcp_pb2.CallToolResponse.Content(
        audio=mcp_pb2.AudioContent(
            data=base64.b64decode(content_block.data),
            mime_type=content_block.mimeType,
        )
    )

  elif isinstance(content_block, mcp_types.EmbeddedResource):
    resource_contents = content_block.resource

    embedded_resource_contents = mcp_pb2.ResourceContents(
        uri=str(resource_contents.uri),
        mime_type=resource_contents.mimeType or "",
    )
    if isinstance(resource_contents, mcp_types.TextResourceContents):
      embedded_resource_contents.text = resource_contents.text
    elif isinstance(resource_contents, mcp_types.BlobResourceContents):
      embedded_resource_contents.blob = base64.b64decode(
          resource_contents.blob
      )

    result = mcp_pb2.CallToolResponse.Content(
        embedded_resource=mcp_pb2.EmbeddedResource(
            contents=embedded_resource_contents
        )
    )

    return result

  elif isinstance(content_block, mcp_types.ResourceLink):  # type: ignore
    return mcp_pb2.CallToolResponse.Content(
        resource_link=mcp_pb2.Resource(
            uri=str(content_block.uri),
            name=content_block.name or "",
            title=content_block.title or "",
            description=content_block.description or "",
            mime_type=content_block.mimeType or "",
        )
    )


def _unstructured_tool_content_to_proto(
    tool_output: Sequence[mcp_types.ContentBlock],
) -> list[mcp_pb2.CallToolResponse.Content]:
  """Converts unstructured tool output to a list of CallToolResponse.Content protos.

  Args:
      tool_output: The unstructured tool output to convert, provided as a
        sequence of ContentBlock objects.

  Returns:
      A list of CallToolResponse.Content protos.
  """

  if not tool_output:
    return []

  contents: list[mcp_pb2.CallToolResponse.Content] = []
  for tool in tool_output:
    content_item = _content_block_to_proto(tool)
    if content_item is not None:
      contents.append(content_item)
    else:
      logger.error("Item is not a valid content block: %s", tool)
      return []

  return contents


def call_tool_result_to_proto(
    result: mcp_types.CallToolResult,
) -> mcp_pb2.CallToolResponse:
  """Converts the mcp_types.CallToolResult object to a CallToolResponse Proto message.

  Args:
      result: The mcp_types.CallToolResult object to convert.

  Returns:
      The converted CallToolResponse Protobuf message.
  """

  call_tool_response = mcp_pb2.CallToolResponse(
      common=mcp_pb2.ResponseFields(),
      is_error=result.isError,
  )

  proto_contents = _unstructured_tool_content_to_proto(
      result.content
  )
  call_tool_response.content.extend(proto_contents)

  if result.structuredContent is not None:
    structured_content_proto = json_format.ParseDict(
        result.structuredContent, struct_pb2.Struct()
    )
    call_tool_response.structured_content = structured_content_proto

  return call_tool_response


def session_queue_item_to_proto(
    item: grpc_session.ServerResponseMessageType,
) -> mcp_pb2.CallToolResponse | None:
  """Converts the session queue item to a CallToolResponse Proto message."""

  if isinstance(item, mcp_types.CallToolResult):
    return call_tool_result_to_proto(item)

  if isinstance(item, mcp_types.ProgressNotification):
    params = item.params
    progress_proto = mcp_pb2.ProgressNotification(
        progress_token=str(params.progressToken),
        progress=params.progress,
        total=params.total,
        message=params.message if params.message is not None else "",
    )

    return mcp_pb2.CallToolResponse(
        common=mcp_pb2.ResponseFields(progress=progress_proto)
    )


def tool_error_to_call_tool_result(
    error: ToolError,
) -> mcp_types.CallToolResult:
  """Converts a ToolError to a CallToolResult."""

  return mcp_types.CallToolResult(
      content=[mcp_types.TextContent(type="text", text=f"{error!r}")],
      structuredContent=None,
      isError=True,
  )


def unify_call_tool_result(
    result: (
        Sequence[mcp_types.ContentBlock]  # Unstructured content
        | dict[str, Any]  # Structured content
        | tuple[Sequence[mcp_types.ContentBlock], dict[str, Any]]  # Both
        | mcp_types.CallToolResult
    ),
) -> mcp_types.CallToolResult:
  """Converts the response object returned by FastMCP.call_tool to a standard mcp_types.CallToolResult object.


  Args:
      result: The result object from FastMCP.call_tool to convert, which can be
        either of -
          - a mcp_types.CallToolResult object.

          or other types for backward compatibility like:
          - unstructured content (Sequence[mcp_types.ContentBlock]),
          - structured content (dict[str, Any]),
          - a tuple of both the above.

  Returns:
      The unified mcp_types.CallToolResult object
  """
  if isinstance(result, mcp_types.CallToolResult):
    return result

  if isinstance(result, tuple):
    unstructured_content, structured_content = result

  elif isinstance(result, dict):
    unstructured_content, structured_content = [], result

  elif isinstance(result, Sequence):
    unstructured_content, structured_content = result, {}

  else:
    raise ValueError(f"Invalid CallToolResult type: {type(result)}")

  return mcp_types.CallToolResult(
      content=unstructured_content,
      structuredContent=structured_content,
      isError=False,
  )

################# End of CallTool Response helper functions ###############
