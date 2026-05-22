"""Utility functions to convert between MCP and Protobuf types."""

import logging
from typing import Any, Sequence

from google.protobuf import json_format
import grpc
from mcp import types as mcp_types
from mcp.server.lowlevel import helper_types as mcp_helper_types
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared import exceptions as mcp_exceptions
import pydantic

from google.protobuf import struct_pb2
from mcp_grpc_transport_proto import mcp_messages_pb2

logger = logging.getLogger(__name__)


def convert_grpc_error_to_mcp_error(
    grpc_error: grpc.aio.AioRpcError,
    error_msg_prefix: str,
) -> mcp_exceptions.McpError:
  """Converts a gRPC error to a MCP error.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      grpc_error: The gRPC error to convert.
      error_msg_prefix: The prefix to add to the error message.

  Returns:
      The converted MCP error.
  """

  if grpc_error.code() is grpc.StatusCode.INVALID_ARGUMENT:
    details = grpc_error.details()
    grpc_error_details = details.lower() if details is not None else ""

    if "parse error" in grpc_error_details:
      mcp_error_code = mcp_types.PARSE_ERROR
    elif "invalid request" in grpc_error_details:
      mcp_error_code = mcp_types.INVALID_REQUEST
    elif "invalid param" in grpc_error_details:
      mcp_error_code = mcp_types.INVALID_PARAMS
    else:
      mcp_error_code = mcp_types.INTERNAL_ERROR

  elif grpc_error.code() is grpc.StatusCode.UNIMPLEMENTED:
    mcp_error_code = mcp_types.METHOD_NOT_FOUND

  elif grpc_error.code() is grpc.StatusCode.NOT_FOUND:
    mcp_error_code = mcp_types.INVALID_REQUEST

  else:
    mcp_error_code = mcp_types.INTERNAL_ERROR

  return mcp_exceptions.McpError(
      mcp_types.ErrorData(
          code=mcp_error_code,
          message=f"{error_msg_prefix}: {grpc_error!r}",
      )
  )


def convert_exception_to_mcp_error(
    error: Exception,
    error_msg_prefix: str,
) -> mcp_exceptions.McpError:
  """Converts an exception to its corresponding MCP error.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      error: The exception to convert.
      error_msg_prefix: The prefix to add to the error message.

  Returns:
      The converted MCP error.
  """

  if isinstance(error, grpc.aio.AioRpcError):
    return convert_grpc_error_to_mcp_error(error, error_msg_prefix)

  if isinstance(error, mcp_exceptions.McpError):
    return error

  if isinstance(error, json_format.ParseError):
    mcp_error_code = mcp_types.PARSE_ERROR

  else:
    mcp_error_code = mcp_types.INTERNAL_ERROR

  return mcp_exceptions.McpError(
      mcp_types.ErrorData(
          code=mcp_error_code,
          message=f"{error_msg_prefix}: {error!r}",
      )
  )

###################### ListResources helper functions ##########################


def list_resources_result_from_proto(
    list_resources_response_proto: mcp_messages_pb2.ListResourcesResponse,
) -> mcp_types.ListResourcesResult:
  """Converts ListResourcesResponse proto to MCP ListResourcesResult object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      list_resources_response_proto: The ListResourcesResponse proto to convert
        from.

  Returns:
      The converted MCP ListResourcesResult object.
  """

  return mcp_types.ListResourcesResult(
      resources=[
          resource_from_proto(resource)
          for resource in list_resources_response_proto.resources
      ]
  )


def resource_from_proto(
    proto: mcp_messages_pb2.Resource,
) -> mcp_types.Resource:
  """Converts a Protobuf Resource message to a MCP Resource type.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      proto: The Protobuf Resource message to convert.

  Returns:
      The converted MCP Resource type.
  """

  return mcp_types.Resource(
      uri=pydantic.AnyUrl(proto.uri),
      name=proto.name,
      title=proto.title if proto.title else None,
      description=proto.description if proto.description else None,
      mimeType=proto.mime_type if proto.mime_type else None,
      size=proto.size if proto.size != 0 else None,
  )


def resource_to_proto(
    resource: mcp_types.Resource
) -> mcp_messages_pb2.Resource:
  """Converts a MCP Resource type to a Protobuf Resource message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      resource: The MCP Resource type to convert.

  Returns:
      The converted Protobuf Resource message.
  """
  return mcp_messages_pb2.Resource(
      uri=str(resource.uri),
      name=resource.name,
      title=resource.title,
      description=resource.description,
      mime_type=resource.mimeType,
      size=resource.size,
  )


################### End of ListResources helper functions ######################

################## ListResourceTemplates helper functions ######################


def list_resource_templates_result_from_proto(
    list_res_templates_resp_proto: mcp_messages_pb2.ListResourceTemplatesResponse,
) -> mcp_types.ListResourceTemplatesResult:
  """Converts ListResourceTemplatesResponse proto to equivalent MCP object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      list_res_templates_resp_proto: The ListResourceTemplatesResponse proto to
        convert from.

  Returns:
      The converted MCP ListResourceTemplatesResult object.
  """

  return mcp_types.ListResourceTemplatesResult(
      resourceTemplates=[
          resource_template_from_proto(resource_template)
          for resource_template in (
              list_res_templates_resp_proto.resource_templates
          )
      ]
  )


def resource_template_from_proto(
    proto: mcp_messages_pb2.ResourceTemplate,
) -> mcp_types.ResourceTemplate:
  """Converts a ResourceTemplate proto message to MCP ResourceTemplate type.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      proto: The ResourceTemplate proto message to convert.

  Returns:
      The converted MCP ResourceTemplate type.
  """
  return mcp_types.ResourceTemplate(
      uriTemplate=proto.uri_template,
      name=proto.name,
      title=proto.title if proto.title else None,
      description=proto.description if proto.description else None,
      mimeType=proto.mime_type if proto.mime_type else None,
  )


def resource_template_to_proto(
    resource_template: mcp_types.ResourceTemplate
) -> mcp_messages_pb2.ResourceTemplate:
  """Converts a MCP ResourceTemplate type to Protobuf ResourceTemplate message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      resource_template: The MCP ResourceTemplate type to convert.

  Returns:
      The converted Protobuf ResourceTemplate message.
  """
  return mcp_messages_pb2.ResourceTemplate(
      uri_template=str(resource_template.uriTemplate),
      name=resource_template.name,
      title=resource_template.title,
      description=resource_template.description,
      mime_type=resource_template.mimeType,
  )


################ End of ListResourceTemplates helper functions #################

###################### ReadResource helper functions ###########################


def read_resource_request_params_from_proto(
    request: mcp_messages_pb2.ReadResourceRequest,
) -> mcp_types.ReadResourceRequestParams:
  """Converts ReadResourceRequest proto to a ReadResourceRequestParams object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      request: The ReadResourceRequest proto message to convert.

  Returns:
      The converted ReadResourceRequestParams object.
  """

  return mcp_types.ReadResourceRequestParams(
      uri=pydantic.AnyUrl(request.uri),
  )


def read_resource_request_params_to_proto(
    request: mcp_types.ReadResourceRequestParams,
) -> mcp_messages_pb2.ReadResourceRequest:
  """Converts ReadResourceRequestParams object to ReadResourceRequest proto.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      request: The ReadResourceRequestParams object to convert.

  Returns:
      The converted ReadResourceRequest proto message.
  """

  return mcp_messages_pb2.ReadResourceRequest(
      uri=str(request.uri),
  )


def read_resource_result_from_proto(
    response: mcp_messages_pb2.ReadResourceResponse,
) -> mcp_types.ReadResourceResult:
  """Converts ReadResourceResponse proto to a ReadResourceResult object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      response: The ReadResourceResponse proto to convert.

  Returns:
      The converted ReadResourceResult object.
  """
  return mcp_types.ReadResourceResult(
      contents=[
          resource_contents_from_proto(resource_contents)
          for resource_contents in response.resource
      ]
  )


def resource_contents_from_proto(
    contents: mcp_messages_pb2.ResourceContents,
) -> mcp_types.TextResourceContents | mcp_types.BlobResourceContents:
  """Converts ResourceContents proto to text/blob ResourceContents object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      contents: The ResourceContents proto to convert.

  Returns:
      The converted Text/Blob ResourceContents object.
  """

  if contents.blob:
    return mcp_types.BlobResourceContents(
        uri=pydantic.AnyUrl(contents.uri),
        mimeType=contents.mime_type if contents.mime_type else None,
        blob=contents.blob.decode(),
    )

  # Note: this considers an empty resource as a text resource by default
  return mcp_types.TextResourceContents(
      uri=pydantic.AnyUrl(contents.uri),
      mimeType=contents.mime_type if contents.mime_type else None,
      text=contents.text,
  )


def resource_contents_to_proto(
    uri: pydantic.AnyUrl,
    resource_contents: mcp_helper_types.ReadResourceContents
) -> mcp_messages_pb2.ResourceContents:
  """Converts a MCP ReadResourceContents type to ResourceContents proto message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      uri: The URI of the resource.
      resource_contents: The MCP ResourceContents type to convert.

  Returns:
      The converted Protobuf ResourceContents message.
  """
  contents = resource_contents.content

  text, blob = (
      ("", contents) if isinstance(contents, bytes) else (contents, b"")
  )

  return mcp_messages_pb2.ResourceContents(
      uri=str(uri),
      mime_type=resource_contents.mime_type or "",
      text=text,
      blob=blob,
  )


#################### End of ReadResource helper functions ######################

###################### ListTools helper functions ##########################


def list_tools_result_from_proto(
    list_tools_response_proto: mcp_messages_pb2.ListToolsResponse,
) -> mcp_types.ListToolsResult:
  """Converts a Protobuf ListToolsResponse message to a MCP ListToolsResult type.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      list_tools_response_proto: The Protobuf ListToolsResponse message to
        convert from.

  Returns:
      The converted MCP ListToolsResult type.
  """
  tools = [tool_from_proto(tool) for tool in list_tools_response_proto.tools]

  return mcp_types.ListToolsResult(
      tools=tools,
  )


def tool_from_proto(tool: mcp_messages_pb2.Tool) -> mcp_types.Tool:
  """Converts a Protobuf Tool message to a MCP Tool type.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      tool: The Protobuf Tool message to convert.

  Returns:
      The converted MCP Tool object.
  """
  try:
    input_schema = json_format.MessageToDict(tool.input_schema)
  except json_format.ParseError as e:
    logger.error("Failed to parse input_schema for tool %s: %s", tool.name, e)
    raise

  try:
    output_schema = None
    if tool.HasField("output_schema"):
      output_schema = json_format.MessageToDict(tool.output_schema)
  except json_format.ParseError as e:
    logger.error("Failed to parse output_schema for tool %s: %s", tool.name, e)
    raise

  return mcp_types.Tool(
      name=tool.name,
      title=tool.title,
      description=tool.description,
      inputSchema=input_schema,
      outputSchema=output_schema,
  )


def tool_to_proto(tool: mcp_types.Tool) -> mcp_messages_pb2.Tool:
  """Converts a MCP Tool type to a Protobuf Tool message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

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

  return mcp_messages_pb2.Tool(
      name=tool.name,
      title=tool.title,
      description=tool.description,
      input_schema=input_schema,
      output_schema=output_schema,
  )

################### End of ListTools helper functions ######################


################### CallTool request helper functions ######################


def call_tool_params_from_proto(
    request: mcp_messages_pb2.CallToolRequest,
) -> mcp_types.CallToolRequestParams:
  """Extracts CallToolRequestParams from a CallToolRequest proto message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

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


def call_tool_params_to_proto(
    call_tool_params: mcp_types.CallToolRequestParams,
) -> mcp_messages_pb2.CallToolRequest:
  """Converts a CallToolRequestParams object to a CallToolRequest proto message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      call_tool_params: The CallToolRequestParams object to convert.

  Returns:
      The converted CallToolRequest proto message.
  """

  arguments = (
      json_format.ParseDict(call_tool_params.arguments, struct_pb2.Struct())
      if call_tool_params.arguments is not None
      else struct_pb2.Struct()
  )

  return mcp_messages_pb2.CallToolRequest(
      request=mcp_messages_pb2.CallToolRequest.Request(
          name=call_tool_params.name,
          arguments=arguments,
      ),
  )


def validate_call_tool_request_proto(
    request: mcp_messages_pb2.CallToolRequest,
) -> None:
  """Validates the CallToolRequest proto message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

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


def _content_block_from_proto(
    content_proto: mcp_messages_pb2.CallToolResponse.Content,
) -> mcp_types.ContentBlock | None:
  """Converts a CallToolResponse.Content Proto message to a MCP type ContentBlock.

  The CallToolResponse.Content Proto message can be one of the following:
  TextContent | ImageContent | AudioContent | Resource | EmbeddedResource

  It is converted to one of the following MCP type ContentBlocks respectively:
  TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource

  Args:
      content_proto: The CallToolResponse.Content Proto message to convert.

  Returns:
      The converted MCP type ContentBlock object or None if the
      content proto is not valid.
  """

  if content_proto.HasField("text"):
    return mcp_types.TextContent(
        type="text",
        text=content_proto.text.text,
    )

  if content_proto.HasField("image"):
    # keep the base64-encoding of the data as is and just convert to string
    return mcp_types.ImageContent(
        type="image",
        data=content_proto.image.data.decode(),
        mimeType=content_proto.image.mime_type,
    )

  if content_proto.HasField("audio"):
    # keep the base64-encoding of the data as is and just convert to string
    return mcp_types.AudioContent(
        type="audio",
        data=content_proto.audio.data.decode(),
        mimeType=content_proto.audio.mime_type,
    )

  if content_proto.HasField("embedded_resource"):
    resource = content_proto.embedded_resource.contents
    if resource.text:
      resource_contents = mcp_types.TextResourceContents(
          uri=resource.uri,
          mimeType=resource.mime_type,
          text=resource.text,
      )
    else:
      # keep the base64-encoding of the blob as is and just convert to string
      resource_contents = mcp_types.BlobResourceContents(
          uri=resource.uri,
          mimeType=resource.mime_type,
          blob=resource.blob.decode(),
      )
    return mcp_types.EmbeddedResource(
        type="resource",
        resource=resource_contents,
    )

  if content_proto.HasField("resource_link"):
    resource = content_proto.resource_link
    return mcp_types.ResourceLink(
        type="resource_link",
        uri=resource.uri,
        name=resource.name,
        title=resource.title,
        description=resource.description,
        mimeType=resource.mime_type,
        size=resource.size,
    )

  return None


def _content_block_to_proto(
    content_block: mcp_types.ContentBlock,
) -> mcp_messages_pb2.CallToolResponse.Content | None:
  """Converts a MCP type ContentBlock to a CallToolResponse.Content Proto message.

  Args:
      content_block: The mcp.types.ContentBlock object to convert.

  Returns:
      The converted CallToolResponse.Content Protobuf message or None if the
      content block is not a valid content block.
  """

  if isinstance(content_block, mcp_types.TextContent):
    return mcp_messages_pb2.CallToolResponse.Content(
        text=mcp_messages_pb2.TextContent(text=content_block.text)
    )

  elif isinstance(content_block, mcp_types.ImageContent):
    # keep the base64-encoding of the received data as is,
    # and just convert to bytes
    return mcp_messages_pb2.CallToolResponse.Content(
        image=mcp_messages_pb2.ImageContent(
            data=content_block.data.encode(),
            mime_type=content_block.mimeType,
        )
    )

  elif isinstance(content_block, mcp_types.AudioContent):
    # keep the base64-encoding of the received data as is,
    # and just convert to bytes
    return mcp_messages_pb2.CallToolResponse.Content(
        audio=mcp_messages_pb2.AudioContent(
            data=content_block.data.encode(),
            mime_type=content_block.mimeType,
        )
    )

  elif isinstance(content_block, mcp_types.EmbeddedResource):
    resource_contents = content_block.resource

    if isinstance(resource_contents, mcp_types.TextResourceContents):
      text, blob = resource_contents.text, b""
    elif isinstance(resource_contents, mcp_types.BlobResourceContents):
      # keep the base64-encoding of the received blob as is,
      # and just convert to bytes
      text, blob = "", resource_contents.blob.encode()
    else:
      text, blob = "", b""

    embedded_resource_contents = mcp_messages_pb2.ResourceContents(
        uri=str(resource_contents.uri),
        mime_type=resource_contents.mimeType or "",
        text=text,
        blob=blob,
    )

    result = mcp_messages_pb2.CallToolResponse.Content(
        embedded_resource=mcp_messages_pb2.EmbeddedResource(
            contents=embedded_resource_contents
        )
    )

    return result

  elif isinstance(content_block, mcp_types.ResourceLink):  # type: ignore
    return mcp_messages_pb2.CallToolResponse.Content(
        resource_link=mcp_messages_pb2.Resource(
            uri=str(content_block.uri),
            name=content_block.name or "",
            title=content_block.title or "",
            description=content_block.description or "",
            mime_type=content_block.mimeType or "",
        )
    )

  return None


def _unstructured_tool_content_from_proto(
    response_contents: Sequence[mcp_messages_pb2.CallToolResponse.Content],
) -> list[mcp_types.ContentBlock]:
  """Converts a list of CallToolResponse.Content protos to a list of ContentBlock objects.

  Args:
      response_contents: The list of CallToolResponse.Content protos to convert.

  Returns:
      A list of ContentBlock objects.
  """

  if not response_contents:
    return []

  contents: list[mcp_types.ContentBlock] = []
  for content_proto in response_contents:
    content_item = _content_block_from_proto(content_proto)
    if content_item is not None:
      contents.append(content_item)
    else:
      logger.error("Found an invalid content proto: %s", content_proto)

  return contents


def _unstructured_tool_content_to_proto(
    tool_output: Sequence[mcp_types.ContentBlock],
) -> list[mcp_messages_pb2.CallToolResponse.Content]:
  """Converts unstructured tool output to a list of CallToolResponse.Content protos.

  Args:
      tool_output: The unstructured tool output to convert, provided as a
        sequence of ContentBlock objects.

  Returns:
      A list of CallToolResponse.Content protos.
  """

  if not tool_output:
    return []

  contents: list[mcp_messages_pb2.CallToolResponse.Content] = []
  for content_block in tool_output:
    content_item = _content_block_to_proto(content_block)
    if content_item is not None:
      contents.append(content_item)
    else:
      logger.error("Item is not a valid content block: %s", content_block)

  return contents


def call_tool_result_from_proto(
    response: mcp_messages_pb2.CallToolResponse,
) -> mcp_types.CallToolResult:
  """Converts a CallToolResponse proto message to a CallToolResult object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      response: The CallToolResponse proto message to convert from.

  Returns:
      The converted CallToolResult object.
  """

  contents = _unstructured_tool_content_from_proto(
      response.content
  )
  call_tool_result = mcp_types.CallToolResult(
      isError=response.is_error,
      content=contents,
  )

  if response.HasField("structured_content"):
    structured_content = json_format.MessageToDict(
        response.structured_content
    )
    call_tool_result.structuredContent = structured_content

  return call_tool_result


def call_tool_result_to_proto(
    result: mcp_types.CallToolResult,
) -> mcp_messages_pb2.CallToolResponse:
  """Converts the mcp_types.CallToolResult object to a CallToolResponse Proto message.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      result: The mcp_types.CallToolResult object to convert.

  Returns:
      The converted CallToolResponse Protobuf message.
  """

  call_tool_response = mcp_messages_pb2.CallToolResponse(
      common=mcp_messages_pb2.ResponseFields(),
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


def tool_error_to_call_tool_result(
    error: ToolError,
) -> mcp_types.CallToolResult:
  """Converts a ToolError to a CallToolResult.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

  Args:
      error: The ToolError to convert.

  Returns:
      The converted CallToolResult object.
  """

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
  """Converts response from FastMCP.call_tool to standard CallToolResult object.

  THIS IS AN EXPERIMENTAL API.
  It is subject to change or removal between minor releases.
  Proceed with caution.

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
