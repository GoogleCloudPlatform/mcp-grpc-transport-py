"""Pure translation between MCP dict payloads and Protobuf messages.

The MCP SDK dispatcher contract is dict-in, dict-out: `send_raw_request`
receives params as a dict (the result of `model_dump(by_alias=True,
mode="json", exclude_none=True)`) and returns a dict that the SDK then
validates against its result Pydantic. Building Pydantic intermediates on
our side just to re-dump them is wasted work, so the routines below operate
on dicts directly.

Field keys follow the SDK's JSON wire aliases (camelCase), matching what
the SDK produces and accepts (`model_validate(..., by_name=False)`).
"""

import logging
from typing import Any, Sequence

from google.protobuf import json_format
from google.protobuf import struct_pb2

from mcp_grpc_transport_proto import mcp_messages_pb2

logger = logging.getLogger(__name__)


# ============================== Struct helpers ==============================

def dict_to_struct(d: dict[str, Any] | None) -> struct_pb2.Struct:
    """Convert a dictionary to a Protobuf Struct message.

    NOTE: Protobuf `Struct` stores all numbers as float64. Round-tripping a
    Python int through Struct yields a float (e.g. 5 → 5.0). Handlers that
    require strict ints must cast explicitly.
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
    """Convert a Protobuf Struct message to a dictionary."""
    try:
        return json_format.MessageToDict(struct)
    except json_format.ParseError:
        logger.exception("Failed to convert Struct to dict")
        raise


# ============================== Common / _meta ==============================

def _set_common_meta(
    proto_with_common: Any,
    params: dict[str, Any] | None,
) -> None:
    """If `_meta` is present in params, populate `proto.common.metadata`."""
    if not params:
        return
    meta = params.get("_meta")
    if meta is None:
        return
    proto_with_common.common.metadata.CopyFrom(dict_to_struct(meta))


def _extract_meta(proto_with_common: Any) -> dict[str, Any] | None:
    """Pull `_meta` (camelCase contract: leading underscore is preserved) from `proto.common.metadata`."""
    if not proto_with_common.HasField("common"):
        return None
    if not proto_with_common.common.HasField("metadata"):
        return None
    return struct_to_dict(proto_with_common.common.metadata)


def _empty_response_common() -> mcp_messages_pb2.ResponseFields:
    return mcp_messages_pb2.ResponseFields()


# ============================== Tools ==============================

def _tool_dict_to_proto(d: dict[str, Any]) -> mcp_messages_pb2.Tool:
    proto = mcp_messages_pb2.Tool(
        name=d.get("name", ""),
        title=d.get("title") or "",
        description=d.get("description") or "",
        input_schema=dict_to_struct(d.get("inputSchema") or {}),
    )
    output_schema = d.get("outputSchema")
    if output_schema is not None:
        proto.output_schema.CopyFrom(dict_to_struct(output_schema))
    return proto


def _tool_proto_to_dict(proto: mcp_messages_pb2.Tool) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": proto.name,
        "inputSchema": struct_to_dict(proto.input_schema),
    }
    if proto.title:
        d["title"] = proto.title
    if proto.description:
        d["description"] = proto.description
    if proto.HasField("output_schema"):
        d["outputSchema"] = struct_to_dict(proto.output_schema)
    return d


def list_tools_result_dict_to_proto(
    result: dict[str, Any],
) -> mcp_messages_pb2.ListToolsResponse:
    """Build a ListToolsResponse from the SDK's dumped ListToolsResult dict."""
    tools = result.get("tools") or []
    return mcp_messages_pb2.ListToolsResponse(
        common=_empty_response_common(),
        tools=[_tool_dict_to_proto(t) for t in tools],
    )


def list_tools_result_proto_to_dict(
    proto: mcp_messages_pb2.ListToolsResponse,
) -> dict[str, Any]:
    """Convert a ListToolsResponse to the dict the SDK will validate."""
    return {"tools": [_tool_proto_to_dict(t) for t in proto.tools]}


# ============================== CallTool params ==============================

def call_tool_params_dict_to_proto(
    params: dict[str, Any],
) -> mcp_messages_pb2.CallToolRequest:
    """Build a CallToolRequest directly from the SDK's params dict.

    Skips Pydantic validation: the SDK has already validated the params
    on its side before handing them to the dispatcher.
    """
    request = mcp_messages_pb2.CallToolRequest.Request(name=params.get("name", ""))
    arguments = params.get("arguments")
    # Preserve presence: `arguments=None` stays unset so the server can tell
    # "no arguments" apart from "empty arguments".
    if arguments is not None:
        request.arguments.CopyFrom(dict_to_struct(arguments))
    proto = mcp_messages_pb2.CallToolRequest(request=request)
    _set_common_meta(proto, params)
    return proto


def call_tool_request_proto_to_params_dict(
    request: mcp_messages_pb2.CallToolRequest,
) -> dict[str, Any]:
    """Convert a CallToolRequest proto into the SDK's params dict shape."""
    result: dict[str, Any] = {"name": request.request.name}
    if request.request.HasField("arguments"):
        result["arguments"] = struct_to_dict(request.request.arguments)
    meta = _extract_meta(request)
    if meta is not None:
        result["_meta"] = meta
    return result


# ============================== CallTool content blocks ==============================

def _content_block_dict_to_proto(
    block: dict[str, Any],
) -> mcp_messages_pb2.CallToolResponse.Content:
    """Convert a single SDK content-block dict to a proto Content message."""
    block_type = block.get("type")
    if block_type == "text":
        return mcp_messages_pb2.CallToolResponse.Content(
            text=mcp_messages_pb2.TextContent(text=block.get("text", "")),
        )
    if block_type == "image":
        return mcp_messages_pb2.CallToolResponse.Content(
            image=mcp_messages_pb2.ImageContent(
                data=block.get("data", "").encode(),
                mime_type=block.get("mimeType") or "",
            ),
        )
    if block_type == "audio":
        return mcp_messages_pb2.CallToolResponse.Content(
            audio=mcp_messages_pb2.AudioContent(
                data=block.get("data", "").encode(),
                mime_type=block.get("mimeType") or "",
            ),
        )
    if block_type == "resource":
        resource = block.get("resource") or {}
        text = resource.get("text") or ""
        blob_str = resource.get("blob") or ""
        return mcp_messages_pb2.CallToolResponse.Content(
            embedded_resource=mcp_messages_pb2.EmbeddedResource(
                contents=mcp_messages_pb2.ResourceContents(
                    uri=str(resource.get("uri", "")),
                    mime_type=resource.get("mimeType") or "",
                    text=text,
                    blob=blob_str.encode() if blob_str else b"",
                ),
            ),
        )
    if block_type == "resource_link":
        return mcp_messages_pb2.CallToolResponse.Content(
            resource_link=mcp_messages_pb2.Resource(
                uri=str(block.get("uri", "")),
                name=block.get("name") or "",
                title=block.get("title") or "",
                description=block.get("description") or "",
                mime_type=block.get("mimeType") or "",
            ),
        )
    raise ValueError(f"Unsupported content block type: {block_type!r}")


def _content_block_proto_to_dict(
    proto: mcp_messages_pb2.CallToolResponse.Content,
) -> dict[str, Any]:
    """Convert a proto Content message to the SDK's content-block dict."""
    if proto.HasField("text"):
        return {"type": "text", "text": proto.text.text}

    if proto.HasField("image"):
        out: dict[str, Any] = {"type": "image", "data": proto.image.data.decode()}
        if proto.image.mime_type:
            out["mimeType"] = proto.image.mime_type
        return out

    if proto.HasField("audio"):
        out = {"type": "audio", "data": proto.audio.data.decode()}
        if proto.audio.mime_type:
            out["mimeType"] = proto.audio.mime_type
        return out

    if proto.HasField("embedded_resource"):
        contents = proto.embedded_resource.contents
        resource: dict[str, Any] = {"uri": contents.uri}
        if contents.mime_type:
            resource["mimeType"] = contents.mime_type
        if contents.blob:
            resource["blob"] = contents.blob.decode()
        else:
            resource["text"] = contents.text
        return {"type": "resource", "resource": resource}

    if proto.HasField("resource_link"):
        link = proto.resource_link
        out = {"type": "resource_link", "uri": link.uri, "name": link.name}
        if link.title:
            out["title"] = link.title
        if link.description:
            out["description"] = link.description
        if link.mime_type:
            out["mimeType"] = link.mime_type
        return out

    raise ValueError("CallToolResponse.Content has no recognised oneof variant set")


# ============================== CallTool result ==============================

def call_tool_result_dict_to_proto(
    result: dict[str, Any],
) -> mcp_messages_pb2.CallToolResponse:
    """Convert the SDK's CallToolResult dict to a CallToolResponse proto."""
    response = mcp_messages_pb2.CallToolResponse(
        common=_empty_response_common(),
        is_error=bool(result.get("isError", False)),
    )
    for block in result.get("content") or []:
        response.content.append(_content_block_dict_to_proto(block))
    structured = result.get("structuredContent")
    if structured is not None:
        response.structured_content.CopyFrom(dict_to_struct(structured))
    return response


def call_tool_result_proto_to_dict(
    proto: mcp_messages_pb2.CallToolResponse,
) -> dict[str, Any]:
    """Convert a CallToolResponse proto to the dict shape the SDK validates."""
    result: dict[str, Any] = {
        "isError": proto.is_error,
        "content": [_content_block_proto_to_dict(c) for c in proto.content],
    }
    if proto.HasField("structured_content"):
        result["structuredContent"] = struct_to_dict(proto.structured_content)
    return result


# ============================== Resources ==============================

def _resource_dict_to_proto(d: dict[str, Any]) -> mcp_messages_pb2.Resource:
    return mcp_messages_pb2.Resource(
        uri=str(d.get("uri", "")),
        name=d.get("name", ""),
        title=d.get("title") or "",
        description=d.get("description") or "",
        mime_type=d.get("mimeType") or "",
        size=d.get("size") or 0,
    )


def _resource_proto_to_dict(proto: mcp_messages_pb2.Resource) -> dict[str, Any]:
    out: dict[str, Any] = {"uri": proto.uri, "name": proto.name}
    if proto.title:
        out["title"] = proto.title
    if proto.description:
        out["description"] = proto.description
    if proto.mime_type:
        out["mimeType"] = proto.mime_type
    if proto.size:
        out["size"] = proto.size
    return out


def list_resources_result_dict_to_proto(
    result: dict[str, Any],
) -> mcp_messages_pb2.ListResourcesResponse:
    resources = result.get("resources") or []
    return mcp_messages_pb2.ListResourcesResponse(
        common=_empty_response_common(),
        resources=[_resource_dict_to_proto(r) for r in resources],
    )


def list_resources_result_proto_to_dict(
    proto: mcp_messages_pb2.ListResourcesResponse,
) -> dict[str, Any]:
    return {"resources": [_resource_proto_to_dict(r) for r in proto.resources]}


# ============================== Resource Templates ==============================

def _resource_template_dict_to_proto(
    d: dict[str, Any],
) -> mcp_messages_pb2.ResourceTemplate:
    return mcp_messages_pb2.ResourceTemplate(
        uri_template=str(d.get("uriTemplate", "")),
        name=d.get("name", ""),
        title=d.get("title") or "",
        description=d.get("description") or "",
        mime_type=d.get("mimeType") or "",
    )


def _resource_template_proto_to_dict(
    proto: mcp_messages_pb2.ResourceTemplate,
) -> dict[str, Any]:
    out: dict[str, Any] = {"uriTemplate": proto.uri_template, "name": proto.name}
    if proto.title:
        out["title"] = proto.title
    if proto.description:
        out["description"] = proto.description
    if proto.mime_type:
        out["mimeType"] = proto.mime_type
    return out


def list_resource_templates_result_dict_to_proto(
    result: dict[str, Any],
) -> mcp_messages_pb2.ListResourceTemplatesResponse:
    templates = result.get("resourceTemplates") or []
    return mcp_messages_pb2.ListResourceTemplatesResponse(
        common=_empty_response_common(),
        resource_templates=[_resource_template_dict_to_proto(t) for t in templates],
    )


def list_resource_templates_result_proto_to_dict(
    proto: mcp_messages_pb2.ListResourceTemplatesResponse,
) -> dict[str, Any]:
    return {
        "resourceTemplates": [
            _resource_template_proto_to_dict(t) for t in proto.resource_templates
        ],
    }


# ============================== ReadResource ==============================

def read_resource_params_dict_to_proto(
    params: dict[str, Any],
) -> mcp_messages_pb2.ReadResourceRequest:
    proto = mcp_messages_pb2.ReadResourceRequest(uri=str(params.get("uri", "")))
    _set_common_meta(proto, params)
    return proto


def read_resource_request_proto_to_params_dict(
    request: mcp_messages_pb2.ReadResourceRequest,
) -> dict[str, Any]:
    result: dict[str, Any] = {"uri": request.uri}
    meta = _extract_meta(request)
    if meta is not None:
        result["_meta"] = meta
    return result


def _resource_contents_dict_to_proto(
    d: dict[str, Any],
) -> mcp_messages_pb2.ResourceContents:
    text = d.get("text") or ""
    blob = d.get("blob") or ""
    return mcp_messages_pb2.ResourceContents(
        uri=str(d.get("uri", "")),
        mime_type=d.get("mimeType") or "",
        text=text,
        blob=blob.encode() if blob else b"",
    )


def _resource_contents_proto_to_dict(
    proto: mcp_messages_pb2.ResourceContents,
) -> dict[str, Any]:
    out: dict[str, Any] = {"uri": proto.uri}
    if proto.mime_type:
        out["mimeType"] = proto.mime_type
    # Proto encodes the variant via the (mutually exclusive) `blob` vs `text` fields.
    if proto.blob:
        out["blob"] = proto.blob.decode()
    else:
        out["text"] = proto.text
    return out


def read_resource_result_dict_to_proto(
    result: dict[str, Any],
) -> mcp_messages_pb2.ReadResourceResponse:
    contents = result.get("contents") or []
    return mcp_messages_pb2.ReadResourceResponse(
        common=_empty_response_common(),
        resource=[_resource_contents_dict_to_proto(c) for c in contents],
    )


def read_resource_result_proto_to_dict(
    proto: mcp_messages_pb2.ReadResourceResponse,
) -> dict[str, Any]:
    return {"contents": [_resource_contents_proto_to_dict(c) for c in proto.resource]}
