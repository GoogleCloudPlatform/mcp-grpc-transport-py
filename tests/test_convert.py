"""Unit tests for schema conversions."""

from google.protobuf import struct_pb2
from mcp import types as mcp_types
from mcp_grpc_transport import convert
from mcp_grpc_transport_proto import mcp_messages_pb2


def test_dict_struct_conversion():
    d = {"key": "value", "nested": {"num": 42, "bool": True}}
    struct = convert.dict_to_struct(d)
    assert isinstance(struct, struct_pb2.Struct)
    assert struct.fields["key"].string_value == "value"
    assert struct.fields["nested"].struct_value.fields["num"].number_value == 42.0
    
    d2 = convert.struct_to_dict(struct)
    assert d2 == d


def test_tool_conversion():
    mcp_tool = mcp_types.Tool(
        name="test_tool",
        description="A test tool",
        input_schema={
            "type": "object",
            "properties": {
                "arg1": {"type": "string"}
            },
            "required": ["arg1"]
        }
    )
    
    proto_tool = convert.tool_to_proto(mcp_tool)
    assert isinstance(proto_tool, mcp_messages_pb2.Tool)
    assert proto_tool.name == "test_tool"
    assert proto_tool.description == "A test tool"
    
    mcp_tool2 = convert.tool_from_proto(proto_tool)
    assert mcp_tool2.name == mcp_tool.name
    assert mcp_tool2.description == mcp_tool.description
    assert mcp_tool2.input_schema == mcp_tool.input_schema


def test_list_tools_result_conversion():
    result = mcp_types.ListToolsResult(
        tools=[
            mcp_types.Tool(name="t1", input_schema={"type": "object"}),
            mcp_types.Tool(name="t2", input_schema={"type": "object"}),
        ]
    )
    
    proto_response = convert.list_tools_result_to_proto(result)
    assert len(proto_response.tools) == 2
    assert proto_response.tools[0].name == "t1"
    
    result2 = convert.list_tools_result_from_proto(proto_response)
    assert len(result2.tools) == 2
    assert result2.tools[0].name == "t1"


def test_call_tool_params_conversion():
    params = mcp_types.CallToolRequestParams(
        name="my_tool",
        arguments={"arg": "val"}
    )
    
    proto_req = convert.call_tool_params_to_proto(params)
    assert proto_req.request.name == "my_tool"
    assert proto_req.request.arguments.fields["arg"].string_value == "val"
    
    params2 = convert.call_tool_params_from_proto(proto_req)
    assert params2.name == "my_tool"
    assert params2.arguments == {"arg": "val"}


def test_call_tool_result_conversion():
    result = mcp_types.CallToolResult(
        is_error=False,
        content=[
            mcp_types.TextContent(type="text", text="hello"),
            mcp_types.ImageContent(type="image", data="dGVzdA==", mime_type="image/png"),
        ]
    )
    
    proto_res = convert.call_tool_result_to_proto(result)
    assert proto_res.is_error is False
    assert len(proto_res.content) == 2
    assert proto_res.content[0].text.text == "hello"
    assert proto_res.content[1].image.data == b"dGVzdA=="
    assert proto_res.content[1].image.mime_type == "image/png"
    
    result2 = convert.call_tool_result_from_proto(proto_res)
    assert result2.is_error is False
    assert len(result2.content) == 2
    assert result2.content[0].text == "hello"
    assert result2.content[1].data == "dGVzdA=="
    assert result2.content[1].mime_type == "image/png"


def test_resource_conversion():
    resource = mcp_types.Resource(
        uri="test://resource",
        name="r1",
        description="desc",
        mime_type="text/plain",
        size=100
    )
    
    proto = convert.resource_to_proto(resource)
    assert proto.uri == "test://resource"
    assert proto.name == "r1"
    assert proto.description == "desc"
    assert proto.mime_type == "text/plain"
    assert proto.size == 100
    
    resource2 = convert.resource_from_proto(proto)
    assert resource2.uri == resource.uri
    assert resource2.name == resource.name
    assert resource2.mime_type == resource.mime_type
    assert resource2.size == resource.size


def test_resource_contents_conversion():
    tc = mcp_types.TextResourceContents(
        uri="test://r1",
        mime_type="text/plain",
        text="hello"
    )
    proto_tc = convert.resource_contents_to_proto(tc)
    assert proto_tc.uri == "test://r1"
    assert proto_tc.text == "hello"
    assert proto_tc.blob == b""
    
    tc2 = convert.resource_contents_from_proto(proto_tc)
    assert isinstance(tc2, mcp_types.TextResourceContents)
    assert tc2.text == "hello"
    
    bc = mcp_types.BlobResourceContents(
        uri="test://r2",
        mime_type="application/octet-stream",
        blob="dGVzdA=="
    )
    proto_bc = convert.resource_contents_to_proto(bc)
    assert proto_bc.uri == "test://r2"
    assert proto_bc.text == ""
    assert proto_bc.blob == b"dGVzdA=="
    
    bc2 = convert.resource_contents_from_proto(proto_bc)
    assert isinstance(bc2, mcp_types.BlobResourceContents)
    assert bc2.blob == "dGVzdA=="


def test_resource_template_conversion():
    rt = mcp_types.ResourceTemplate(
        uri_template="test://{name}",
        name="t1",
        description="desc",
        mime_type="text/plain"
    )
    proto = convert.resource_template_to_proto(rt)
    assert proto.uri_template == "test://{name}"
    assert proto.name == "t1"
    assert proto.description == "desc"
    assert proto.mime_type == "text/plain"
    
    rt2 = convert.resource_template_from_proto(proto)
    assert rt2.uri_template == rt.uri_template
    assert rt2.name == rt.name
    assert rt2.mime_type == rt.mime_type


def test_list_resource_templates_result_conversion():
    result = mcp_types.ListResourceTemplatesResult(
        resource_templates=[
            mcp_types.ResourceTemplate(uri_template="t1", name="n1"),
            mcp_types.ResourceTemplate(uri_template="t2", name="n2"),
        ]
    )
    proto = convert.list_resource_templates_result_to_proto(result)
    assert len(proto.resource_templates) == 2
    assert proto.resource_templates[0].name == "n1"
    
    result2 = convert.list_resource_templates_result_from_proto(proto)
    assert len(result2.resource_templates) == 2
    assert result2.resource_templates[0].name == "n1"


def test_read_resource_result_conversion():
    result = mcp_types.ReadResourceResult(
        contents=[
            mcp_types.TextResourceContents(uri="test://r1", text="t1"),
        ]
    )
    proto = convert.read_resource_result_to_proto(result)
    assert len(proto.resource) == 1
    assert proto.resource[0].text == "t1"
    
    result2 = convert.read_resource_result_from_proto(proto)
    assert len(result2.contents) == 1
    assert result2.contents[0].text == "t1"


def test_resource_contents_invalid_type():
    import pytest
    with pytest.raises(ValueError, match="Invalid resource contents type"):
        convert.resource_contents_to_proto("not a resource contents object")


def test_content_block_audio_and_link_conversion():
    # Test AudioContent
    audio = mcp_types.AudioContent(type="audio", data="dGVzdA==", mime_type="audio/wav")
    proto_audio = convert._content_block_to_proto(audio)
    assert proto_audio.HasField("audio")
    assert proto_audio.audio.data == b"dGVzdA=="
    assert proto_audio.audio.mime_type == "audio/wav"
    
    audio2 = convert._content_block_from_proto(proto_audio)
    assert isinstance(audio2, mcp_types.AudioContent)
    assert audio2.data == "dGVzdA=="
    assert audio2.mime_type == "audio/wav"
    
    # Test ResourceLink
    link = mcp_types.ResourceLink(
        type="resource_link",
        uri="test://link",
        name="l1",
        title="t1",
        description="d1",
        mime_type="text/html"
    )
    proto_link = convert._content_block_to_proto(link)
    assert proto_link.HasField("resource_link")
    assert proto_link.resource_link.uri == "test://link"
    assert proto_link.resource_link.name == "l1"
    
    link2 = convert._content_block_from_proto(proto_link)
    assert isinstance(link2, mcp_types.ResourceLink)
    assert link2.uri == "test://link"
    assert link2.name == "l1"
    assert link2.title == "t1"

