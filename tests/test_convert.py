"""Unit tests for the dict <-> protobuf conversion layer.

The converters in `convert.py` work directly on the dict shape that the SDK
hands the dispatcher (params dicts produced by `model_dump(by_alias=True,
mode="json", exclude_none=True)`) and that the SDK expects back. These tests
exercise round-trip fidelity and edge cases without going through Pydantic.
"""

import pytest
from google.protobuf import struct_pb2

from mcp_grpc_transport import convert
from mcp_grpc_transport_proto import mcp_messages_pb2


# ----------------------------- Struct helpers -----------------------------

def test_dict_struct_round_trip():
    d = {"key": "value", "nested": {"num": 42, "bool": True}}
    struct = convert.dict_to_struct(d)
    assert isinstance(struct, struct_pb2.Struct)
    assert struct.fields["key"].string_value == "value"
    assert struct.fields["nested"].struct_value.fields["num"].number_value == 42.0
    assert convert.struct_to_dict(struct) == d


def test_dict_to_struct_handles_none():
    struct = convert.dict_to_struct(None)
    assert isinstance(struct, struct_pb2.Struct)
    assert len(struct.fields) == 0


# ----------------------------- ListTools -----------------------------

def test_list_tools_result_round_trip():
    d = {
        "tools": [
            {
                "name": "add",
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                    "required": ["a", "b"],
                },
            },
            {"name": "minimal", "inputSchema": {"type": "object"}},
        ],
    }
    proto = convert.list_tools_result_dict_to_proto(d)
    assert len(proto.tools) == 2
    assert proto.tools[0].name == "add"
    assert proto.tools[0].description == "Add two numbers"

    back = convert.list_tools_result_proto_to_dict(proto)
    assert back == d


def test_list_tools_result_includes_output_schema_when_set():
    d = {
        "tools": [
            {
                "name": "calc",
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "number"},
            }
        ]
    }
    proto = convert.list_tools_result_dict_to_proto(d)
    assert proto.tools[0].HasField("output_schema")
    back = convert.list_tools_result_proto_to_dict(proto)
    assert back["tools"][0]["outputSchema"] == {"type": "number"}


def test_list_tools_omits_optional_fields_in_dict():
    """Empty proto string fields must NOT surface in the dict (SDK uses exclude_none)."""
    proto = mcp_messages_pb2.ListToolsResponse()
    proto.tools.append(mcp_messages_pb2.Tool(name="t", input_schema=convert.dict_to_struct({"type": "object"})))
    d = convert.list_tools_result_proto_to_dict(proto)
    assert d == {"tools": [{"name": "t", "inputSchema": {"type": "object"}}]}


# ----------------------------- CallTool params -----------------------------

def test_call_tool_params_round_trip():
    d = {"name": "echo", "arguments": {"msg": "hi"}}
    proto = convert.call_tool_params_dict_to_proto(d)
    assert proto.request.name == "echo"
    assert proto.request.HasField("arguments")
    assert proto.request.arguments.fields["msg"].string_value == "hi"

    back = convert.call_tool_request_proto_to_params_dict(proto)
    assert back == d


def test_call_tool_params_arguments_presence_distinguishes_none_from_empty():
    """`arguments=None` keeps the proto field unset; `arguments={}` sets it."""
    proto_none = convert.call_tool_params_dict_to_proto({"name": "x"})  # no arguments
    assert not proto_none.request.HasField("arguments")
    assert "arguments" not in convert.call_tool_request_proto_to_params_dict(proto_none)

    proto_empty = convert.call_tool_params_dict_to_proto({"name": "x", "arguments": {}})
    assert proto_empty.request.HasField("arguments")
    assert convert.call_tool_request_proto_to_params_dict(proto_empty)["arguments"] == {}


def test_call_tool_params_meta_round_trip():
    d = {"name": "x", "arguments": {"a": 1}, "_meta": {"traceId": "abc"}}
    proto = convert.call_tool_params_dict_to_proto(d)
    assert proto.HasField("common")
    assert proto.common.HasField("metadata")

    back = convert.call_tool_request_proto_to_params_dict(proto)
    assert back["_meta"] == {"traceId": "abc"}
    # Numbers in Struct become floats: a=1 -> 1.0 after Struct round-trip.
    assert back["arguments"] == {"a": 1.0}


# ----------------------------- CallTool result -----------------------------

def test_call_tool_result_text_round_trip():
    d = {"isError": False, "content": [{"type": "text", "text": "hello"}]}
    proto = convert.call_tool_result_dict_to_proto(d)
    assert proto.is_error is False
    assert proto.content[0].text.text == "hello"

    back = convert.call_tool_result_proto_to_dict(proto)
    assert back == d


def test_call_tool_result_image_audio_round_trip():
    d = {
        "isError": False,
        "content": [
            {"type": "image", "data": "dGVzdA==", "mimeType": "image/png"},
            {"type": "audio", "data": "dGVzdA==", "mimeType": "audio/wav"},
        ],
    }
    proto = convert.call_tool_result_dict_to_proto(d)
    assert proto.content[0].image.data == b"dGVzdA=="
    assert proto.content[0].image.mime_type == "image/png"
    assert proto.content[1].audio.data == b"dGVzdA=="

    back = convert.call_tool_result_proto_to_dict(proto)
    assert back == d


def test_call_tool_result_embedded_resource_text_round_trip():
    d = {
        "isError": False,
        "content": [
            {
                "type": "resource",
                "resource": {"uri": "x://r", "mimeType": "text/plain", "text": "body"},
            }
        ],
    }
    proto = convert.call_tool_result_dict_to_proto(d)
    assert proto.content[0].embedded_resource.contents.text == "body"
    back = convert.call_tool_result_proto_to_dict(proto)
    assert back == d


def test_call_tool_result_embedded_resource_blob_round_trip():
    d = {
        "isError": False,
        "content": [
            {
                "type": "resource",
                "resource": {"uri": "x://r", "mimeType": "image/png", "blob": "dGVzdA=="},
            }
        ],
    }
    proto = convert.call_tool_result_dict_to_proto(d)
    assert proto.content[0].embedded_resource.contents.blob == b"dGVzdA=="
    back = convert.call_tool_result_proto_to_dict(proto)
    assert back == d


def test_call_tool_result_resource_link_round_trip():
    d = {
        "isError": False,
        "content": [
            {
                "type": "resource_link",
                "uri": "x://link",
                "name": "l",
                "title": "Link",
                "description": "desc",
                "mimeType": "text/html",
            }
        ],
    }
    proto = convert.call_tool_result_dict_to_proto(d)
    assert proto.content[0].resource_link.uri == "x://link"

    back = convert.call_tool_result_proto_to_dict(proto)
    assert back == d


def test_call_tool_result_structured_content_round_trip():
    d = {
        "isError": False,
        "content": [],
        "structuredContent": {"answer": 42},
    }
    proto = convert.call_tool_result_dict_to_proto(d)
    assert proto.HasField("structured_content")

    back = convert.call_tool_result_proto_to_dict(proto)
    # Struct turns 42 into 42.0; the comparison should reflect that.
    assert back["structuredContent"] == {"answer": 42.0}
    assert back["isError"] is False
    assert back["content"] == []


def test_call_tool_result_unknown_content_type_raises():
    with pytest.raises(ValueError, match="Unsupported content block type"):
        convert.call_tool_result_dict_to_proto({"content": [{"type": "alien"}]})


def test_content_block_from_proto_raises_on_empty_oneof():
    empty = mcp_messages_pb2.CallToolResponse.Content()
    with pytest.raises(ValueError, match="no recognised oneof variant"):
        convert._content_block_proto_to_dict(empty)


# ----------------------------- Resources -----------------------------

def test_list_resources_round_trip():
    d = {
        "resources": [
            {"uri": "x://a", "name": "a", "mimeType": "text/plain", "size": 100},
            {"uri": "x://b", "name": "b"},  # minimal: only required fields
        ]
    }
    proto = convert.list_resources_result_dict_to_proto(d)
    assert proto.resources[0].size == 100
    assert proto.resources[1].size == 0

    back = convert.list_resources_result_proto_to_dict(proto)
    assert back == d


def test_resource_omits_unset_optionals_in_dict():
    """Empty proto strings must not surface in the dict — they round-trip as absent."""
    proto = mcp_messages_pb2.ListResourcesResponse()
    proto.resources.append(mcp_messages_pb2.Resource(uri="x://x", name="x"))
    d = convert.list_resources_result_proto_to_dict(proto)
    assert d == {"resources": [{"uri": "x://x", "name": "x"}]}


# ----------------------------- Resource Templates -----------------------------

def test_list_resource_templates_round_trip():
    d = {
        "resourceTemplates": [
            {"uriTemplate": "x://{n}", "name": "t", "mimeType": "text/plain"},
            {"uriTemplate": "y://{n}", "name": "u"},
        ]
    }
    proto = convert.list_resource_templates_result_dict_to_proto(d)
    assert proto.resource_templates[0].uri_template == "x://{n}"

    back = convert.list_resource_templates_result_proto_to_dict(proto)
    assert back == d


# ----------------------------- ReadResource -----------------------------

def test_read_resource_params_round_trip():
    d = {"uri": "x://r"}
    proto = convert.read_resource_params_dict_to_proto(d)
    assert proto.uri == "x://r"

    back = convert.read_resource_request_proto_to_params_dict(proto)
    assert back == d


def test_read_resource_params_meta_round_trip():
    d = {"uri": "x://r", "_meta": {"trace": "t"}}
    proto = convert.read_resource_params_dict_to_proto(d)
    assert proto.common.HasField("metadata")
    back = convert.read_resource_request_proto_to_params_dict(proto)
    assert back == d


def test_read_resource_result_text_round_trip():
    d = {"contents": [{"uri": "x://r", "mimeType": "text/plain", "text": "hi"}]}
    proto = convert.read_resource_result_dict_to_proto(d)
    assert proto.resource[0].text == "hi"
    assert proto.resource[0].blob == b""

    back = convert.read_resource_result_proto_to_dict(proto)
    assert back == d


def test_read_resource_result_blob_round_trip():
    d = {"contents": [{"uri": "x://r", "mimeType": "application/octet-stream", "blob": "dGVzdA=="}]}
    proto = convert.read_resource_result_dict_to_proto(d)
    assert proto.resource[0].blob == b"dGVzdA=="

    back = convert.read_resource_result_proto_to_dict(proto)
    assert back == d
