"""Pure translation functions between MCP types/dicts and Protobuf messages.

This module maps between python-sdk V2 snake_case model attributes and generated
Protobuf snake_case message fields, performing bytes-to-string encoding (like image/audio base64)
and structural conversions.
"""

import logging
from typing import Any, Sequence

from google.protobuf import json_format
from google.protobuf import struct_pb2
from mcp import types as mcp_types
from mcp.server.lowlevel import helper_types as mcp_helper_types

from mcp_grpc_transport_proto import mcp_messages_pb2

logger = logging.getLogger(__name__)


# Struct helper
def dict_to_struct(d: dict[str, Any] | None) -> struct_pb2.Struct:
    """Converts a dictionary to a Protobuf Struct message.
    
    NOTE: Protobuf Struct stores all numbers as float64 (double). When converting 
    dict -> Struct -> dict, any Python integers will be deserialized as floats (e.g. 5 becomes 5.0).
    Handlers expecting strict integer types must explicitly cast them.
    """
    struct = struct_pb2.Struct()
    if d:
        try:
            json_format.ParseDict(d, struct)
        except json_format.ParseError:
            logger.exception("Failed to parse dict to Struct (dict: %s)", d)
            raise
    return struct


def struct_to_dict(struct: struct_pb2.Struct) -> dict[str, Any]:
    """Converts a Protobuf Struct message to a dictionary."""
    try:
        return json_format.MessageToDict(struct)
    except json_format.ParseError:
        logger.exception("Failed to convert Struct to dict")
        raise


# Resources
def list_resources_result_from_proto(
    list_resources_response_proto: mcp_messages_pb2.ListResourcesResponse,
) -> mcp_types.ListResourcesResult:
    """Converts ListResourcesResponse proto to MCP ListResourcesResult object."""
    return mcp_types.ListResourcesResult(
        resources=[
            resource_from_proto(resource)
            for resource in list_resources_response_proto.resources
        ]
    )


def resource_from_proto(
    proto: mcp_messages_pb2.Resource,
) -> mcp_types.Resource:
    """Converts a Protobuf Resource message to a MCP Resource type."""
    return mcp_types.Resource(
        uri=proto.uri,
        name=proto.name,
        title=proto.title if proto.title else None,
        description=proto.description if proto.description else None,
        mime_type=proto.mime_type if proto.mime_type else None,
        size=proto.size if proto.size != 0 else None,
    )


def resource_to_proto(
    resource: mcp_types.Resource
) -> mcp_messages_pb2.Resource:
    """Converts a MCP Resource type to a Protobuf Resource message."""
    return mcp_messages_pb2.Resource(
        uri=str(resource.uri),
        name=resource.name,
        title=resource.title,
        description=resource.description,
        mime_type=resource.mime_type,
        size=resource.size,
    )


def list_resources_result_to_proto(
    result: mcp_types.ListResourcesResult,
) -> mcp_messages_pb2.ListResourcesResponse:
    """Converts ListResourcesResult to ListResourcesResponse proto message."""
    return mcp_messages_pb2.ListResourcesResponse(
        common=mcp_messages_pb2.ResponseFields(),
        resources=[resource_to_proto(resource) for resource in result.resources],
    )


# Resource Templates
def list_resource_templates_result_from_proto(
    list_res_templates_resp_proto: mcp_messages_pb2.ListResourceTemplatesResponse,
) -> mcp_types.ListResourceTemplatesResult:
    """Converts ListResourceTemplatesResponse proto to equivalent MCP object."""
    return mcp_types.ListResourceTemplatesResult(
        resource_templates=[
            resource_template_from_proto(resource_template)
            for resource_template in (
                list_res_templates_resp_proto.resource_templates
            )
        ]
    )


def resource_template_from_proto(
    proto: mcp_messages_pb2.ResourceTemplate,
) -> mcp_types.ResourceTemplate:
    """Converts a ResourceTemplate proto message to MCP ResourceTemplate type."""
    return mcp_types.ResourceTemplate(
        uri_template=proto.uri_template,
        name=proto.name,
        title=proto.title if proto.title else None,
        description=proto.description if proto.description else None,
        mime_type=proto.mime_type if proto.mime_type else None,
    )


def resource_template_to_proto(
    resource_template: mcp_types.ResourceTemplate
) -> mcp_messages_pb2.ResourceTemplate:
    """Converts a MCP ResourceTemplate type to Protobuf ResourceTemplate message."""
    return mcp_messages_pb2.ResourceTemplate(
        uri_template=str(resource_template.uri_template),
        name=resource_template.name,
        title=resource_template.title,
        description=resource_template.description,
        mime_type=resource_template.mime_type,
    )


def list_resource_templates_result_to_proto(
    result: mcp_types.ListResourceTemplatesResult,
) -> mcp_messages_pb2.ListResourceTemplatesResponse:
    """Converts ListResourceTemplatesResult to ListResourceTemplatesResponse proto message."""
    return mcp_messages_pb2.ListResourceTemplatesResponse(
        common=mcp_messages_pb2.ResponseFields(),
        resource_templates=[
            resource_template_to_proto(rt) for rt in result.resource_templates
        ],
    )


# Resource Contents
def read_resource_request_params_from_proto(
    request: mcp_messages_pb2.ReadResourceRequest,
) -> mcp_types.ReadResourceRequestParams:
    """Converts ReadResourceRequest proto to a ReadResourceRequestParams object."""
    return mcp_types.ReadResourceRequestParams(
        uri=request.uri,
    )


def read_resource_request_params_to_proto(
    request: mcp_types.ReadResourceRequestParams,
) -> mcp_messages_pb2.ReadResourceRequest:
    """Converts ReadResourceRequestParams object to ReadResourceRequest proto."""
    return mcp_messages_pb2.ReadResourceRequest(
        uri=str(request.uri),
    )


def read_resource_result_from_proto(
    response: mcp_messages_pb2.ReadResourceResponse,
) -> mcp_types.ReadResourceResult:
    """Converts ReadResourceResponse proto to a ReadResourceResult object."""
    return mcp_types.ReadResourceResult(
        contents=[
            resource_contents_from_proto(resource_contents)
            for resource_contents in response.resource
        ]
    )


def resource_contents_from_proto(
    contents: mcp_messages_pb2.ResourceContents,
) -> mcp_types.TextResourceContents | mcp_types.BlobResourceContents:
    """Converts ResourceContents proto to text/blob ResourceContents object."""
    if contents.blob:
        return mcp_types.BlobResourceContents(
            uri=contents.uri,
            mime_type=contents.mime_type if contents.mime_type else None,
            blob=contents.blob.decode(),
        )
    return mcp_types.TextResourceContents(
        uri=contents.uri,
        mime_type=contents.mime_type if contents.mime_type else None,
        text=contents.text,
    )


def resource_contents_to_proto(
    resource_contents: mcp_types.TextResourceContents | mcp_types.BlobResourceContents
) -> mcp_messages_pb2.ResourceContents:
    """Converts a MCP Text/Blob ResourceContents type to ResourceContents proto message."""
    if isinstance(resource_contents, mcp_types.TextResourceContents):
        return mcp_messages_pb2.ResourceContents(
            uri=str(resource_contents.uri),
            mime_type=resource_contents.mime_type or "",
            text=resource_contents.text,
            blob=b"",
        )
    elif isinstance(resource_contents, mcp_types.BlobResourceContents):
        return mcp_messages_pb2.ResourceContents(
            uri=str(resource_contents.uri),
            mime_type=resource_contents.mime_type or "",
            text="",
            blob=resource_contents.blob.encode(),
        )
    raise ValueError(f"Invalid resource contents type: {type(resource_contents)}")


def read_resource_result_to_proto(
    result: mcp_types.ReadResourceResult,
) -> mcp_messages_pb2.ReadResourceResponse:
    """Converts ReadResourceResult to ReadResourceResponse proto message."""
    return mcp_messages_pb2.ReadResourceResponse(
        common=mcp_messages_pb2.ResponseFields(),
        resource=[resource_contents_to_proto(c) for c in result.contents],
    )


# Tools
def list_tools_result_from_proto(
    list_tools_response_proto: mcp_messages_pb2.ListToolsResponse,
) -> mcp_types.ListToolsResult:
    """Converts a Protobuf ListToolsResponse message to a MCP ListToolsResult type."""
    return mcp_types.ListToolsResult(
        tools=[tool_from_proto(tool) for tool in list_tools_response_proto.tools]
    )


def tool_from_proto(tool: mcp_messages_pb2.Tool) -> mcp_types.Tool:
    """Converts a Protobuf Tool message to a MCP Tool type."""
    input_schema = struct_to_dict(tool.input_schema)
    output_schema = None
    if tool.HasField("output_schema"):
        output_schema = struct_to_dict(tool.output_schema)

    return mcp_types.Tool(
        name=tool.name,
        title=tool.title if tool.title else None,
        description=tool.description if tool.description else None,
        input_schema=input_schema,
        output_schema=output_schema,
    )


def tool_to_proto(tool: mcp_types.Tool) -> mcp_messages_pb2.Tool:
    """Converts a MCP Tool type to a Protobuf Tool message."""
    input_schema = dict_to_struct(tool.input_schema)
    output_schema = None
    if tool.output_schema is not None:
        output_schema = dict_to_struct(tool.output_schema)

    return mcp_messages_pb2.Tool(
        name=tool.name,
        title=tool.title or "",
        description=tool.description or "",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def list_tools_result_to_proto(
    result: mcp_types.ListToolsResult,
) -> mcp_messages_pb2.ListToolsResponse:
    """Converts ListToolsResult to ListToolsResponse proto message."""
    return mcp_messages_pb2.ListToolsResponse(
        common=mcp_messages_pb2.ResponseFields(),
        tools=[tool_to_proto(tool) for tool in result.tools],
    )


# CallTool Params
def call_tool_params_from_proto(
    request: mcp_messages_pb2.CallToolRequest,
) -> mcp_types.CallToolRequestParams:
    """Extracts CallToolRequestParams from a CallToolRequest proto message."""
    arguments = None
    if request.request.HasField("arguments"):
        arguments = struct_to_dict(request.request.arguments)

    return mcp_types.CallToolRequestParams(
        name=request.request.name,
        arguments=arguments,
    )


def call_tool_params_to_proto(
    call_tool_params: mcp_types.CallToolRequestParams,
) -> mcp_messages_pb2.CallToolRequest:
    """Converts a CallToolRequestParams object to a CallToolRequest proto message."""
    arguments = (
        dict_to_struct(call_tool_params.arguments)
        if call_tool_params.arguments is not None
        else struct_pb2.Struct()
    )
    return mcp_messages_pb2.CallToolRequest(
        request=mcp_messages_pb2.CallToolRequest.Request(
            name=call_tool_params.name,
            arguments=arguments,
        ),
    )


# CallTool Content Blocks
def _content_block_from_proto(
    content_proto: mcp_messages_pb2.CallToolResponse.Content,
) -> mcp_types.ContentBlock | None:
    """Converts a CallToolResponse.Content Proto message to a MCP type ContentBlock."""
    if content_proto.HasField("text"):
        return mcp_types.TextContent(
            type="text",
            text=content_proto.text.text,
        )

    if content_proto.HasField("image"):
        return mcp_types.ImageContent(
            type="image",
            data=content_proto.image.data.decode(),
            mime_type=content_proto.image.mime_type,
        )

    if content_proto.HasField("audio"):
        return mcp_types.AudioContent(
            type="audio",
            data=content_proto.audio.data.decode(),
            mime_type=content_proto.audio.mime_type,
        )

    if content_proto.HasField("embedded_resource"):
        resource = content_proto.embedded_resource.contents
        if resource.text:
            resource_contents = mcp_types.TextResourceContents(
                uri=resource.uri,
                mime_type=resource.mime_type if resource.mime_type else None,
                text=resource.text,
            )
        else:
            resource_contents = mcp_types.BlobResourceContents(
                uri=resource.uri,
                mime_type=resource.mime_type if resource.mime_type else None,
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
            title=resource.title if resource.title else None,
            description=resource.description if resource.description else None,
            mime_type=resource.mime_type if resource.mime_type else None,
        )

    return None


def _content_block_to_proto(
    content_block: mcp_types.ContentBlock,
) -> mcp_messages_pb2.CallToolResponse.Content | None:
    """Converts a MCP type ContentBlock to a CallToolResponse.Content Proto message."""
    if isinstance(content_block, mcp_types.TextContent):
        return mcp_messages_pb2.CallToolResponse.Content(
            text=mcp_messages_pb2.TextContent(text=content_block.text)
        )

    elif isinstance(content_block, mcp_types.ImageContent):
        return mcp_messages_pb2.CallToolResponse.Content(
            image=mcp_messages_pb2.ImageContent(
                data=content_block.data.encode(),
                mime_type=content_block.mime_type,
            )
        )

    elif isinstance(content_block, mcp_types.AudioContent):
        return mcp_messages_pb2.CallToolResponse.Content(
            audio=mcp_messages_pb2.AudioContent(
                data=content_block.data.encode(),
                mime_type=content_block.mime_type,
            )
        )

    elif isinstance(content_block, mcp_types.EmbeddedResource):
        resource_contents = content_block.resource
        if isinstance(resource_contents, mcp_types.TextResourceContents):
            text, blob = resource_contents.text, b""
        elif isinstance(resource_contents, mcp_types.BlobResourceContents):
            text, blob = "", resource_contents.blob.encode()
        else:
            text, blob = "", b""

        embedded_resource_contents = mcp_messages_pb2.ResourceContents(
            uri=str(resource_contents.uri),
            mime_type=resource_contents.mime_type or "",
            text=text,
            blob=blob,
        )
        return mcp_messages_pb2.CallToolResponse.Content(
            embedded_resource=mcp_messages_pb2.EmbeddedResource(
                contents=embedded_resource_contents
            )
        )

    elif isinstance(content_block, mcp_types.ResourceLink):
        return mcp_messages_pb2.CallToolResponse.Content(
            resource_link=mcp_messages_pb2.Resource(
                uri=str(content_block.uri),
                name=content_block.name or "",
                title=content_block.title or "",
                description=content_block.description or "",
                mime_type=content_block.mime_type or "",
            )
        )

    return None


def _unstructured_tool_content_from_proto(
    response_contents: Sequence[mcp_messages_pb2.CallToolResponse.Content],
) -> list[mcp_types.ContentBlock]:
    """Converts a list of CallToolResponse.Content protos to a list of ContentBlock objects."""
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
    """Converts unstructured tool output to a list of CallToolResponse.Content protos."""
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


# CallTool Result
def call_tool_result_from_proto(
    response: mcp_messages_pb2.CallToolResponse,
) -> mcp_types.CallToolResult:
    """Converts a CallToolResponse proto message to a CallToolResult object."""
    contents = _unstructured_tool_content_from_proto(response.content)
    call_tool_result = mcp_types.CallToolResult(
        is_error=response.is_error,
        content=contents,
    )

    if response.HasField("structured_content"):
        structured_content = struct_to_dict(response.structured_content)
        call_tool_result.structured_content = structured_content

    return call_tool_result


def call_tool_result_to_proto(
    result: mcp_types.CallToolResult,
) -> mcp_messages_pb2.CallToolResponse:
    """Converts the mcp_types.CallToolResult object to a CallToolResponse Proto message."""
    call_tool_response = mcp_messages_pb2.CallToolResponse(
        common=mcp_messages_pb2.ResponseFields(),
        is_error=result.is_error,
    )

    proto_contents = _unstructured_tool_content_to_proto(result.content)
    call_tool_response.content.extend(proto_contents)

    if result.structured_content is not None:
        structured_content_proto = dict_to_struct(result.structured_content)
        call_tool_response.structured_content = structured_content_proto

    return call_tool_response
