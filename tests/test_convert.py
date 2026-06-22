"""Unit tests for the dict <-> protobuf conversion layer.

The converters in `convert.py` work directly on the dict shape that the SDK
hands the dispatcher (params dicts produced by `model_dump(by_alias=True,
mode="json", exclude_none=True)`) and that the SDK expects back. These tests
exercise round-trip fidelity and edge cases without going through Pydantic.
"""

from absl.testing import absltest
from google.protobuf import struct_pb2

from mcp_grpc_transport import convert
from mcp_grpc_transport_proto import mcp_messages_pb2


class StructHelpersTest(absltest.TestCase):

    def test_dict_struct_round_trip(self):
        d = {"key": "value", "nested": {"num": 42, "bool": True}}
        struct = convert.dict_to_struct(d)
        self.assertIsInstance(struct, struct_pb2.Struct)
        self.assertEqual(struct.fields["key"].string_value, "value")
        self.assertEqual(struct.fields["nested"].struct_value.fields["num"].number_value, 42.0)
        self.assertEqual(convert.struct_to_dict(struct), d)

    def test_dict_to_struct_handles_none(self):
        struct = convert.dict_to_struct(None)
        self.assertIsInstance(struct, struct_pb2.Struct)
        self.assertEqual(len(struct.fields), 0)


class ListToolsTest(absltest.TestCase):

    def test_round_trip(self):
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
        self.assertLen(proto.tools, 2)
        self.assertEqual(proto.tools[0].name, "add")
        self.assertEqual(proto.tools[0].description, "Add two numbers")

        self.assertEqual(convert.list_tools_result_proto_to_dict(proto), d)

    def test_includes_output_schema_when_set(self):
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
        self.assertTrue(proto.tools[0].HasField("output_schema"))
        back = convert.list_tools_result_proto_to_dict(proto)
        self.assertEqual(back["tools"][0]["outputSchema"], {"type": "number"})

    def test_omits_optional_fields_in_dict(self):
        """Empty proto string fields must NOT surface in the dict (SDK uses exclude_none)."""
        proto = mcp_messages_pb2.ListToolsResponse()
        proto.tools.append(
            mcp_messages_pb2.Tool(name="t", input_schema=convert.dict_to_struct({"type": "object"}))
        )
        d = convert.list_tools_result_proto_to_dict(proto)
        self.assertEqual(d, {"tools": [{"name": "t", "inputSchema": {"type": "object"}}]})


class CallToolParamsTest(absltest.TestCase):

    def test_round_trip(self):
        d = {"name": "echo", "arguments": {"msg": "hi"}}
        proto = convert.call_tool_params_dict_to_proto(d)
        self.assertEqual(proto.request.name, "echo")
        self.assertTrue(proto.request.HasField("arguments"))
        self.assertEqual(proto.request.arguments.fields["msg"].string_value, "hi")

        self.assertEqual(convert.call_tool_request_proto_to_params_dict(proto), d)

    def test_arguments_presence_distinguishes_none_from_empty(self):
        """`arguments=None` keeps the proto field unset; `arguments={}` sets it."""
        proto_none = convert.call_tool_params_dict_to_proto({"name": "x"})  # no arguments
        self.assertFalse(proto_none.request.HasField("arguments"))
        self.assertNotIn("arguments", convert.call_tool_request_proto_to_params_dict(proto_none))

        proto_empty = convert.call_tool_params_dict_to_proto({"name": "x", "arguments": {}})
        self.assertTrue(proto_empty.request.HasField("arguments"))
        self.assertEqual(convert.call_tool_request_proto_to_params_dict(proto_empty)["arguments"], {})

    def test_meta_round_trip(self):
        d = {"name": "x", "arguments": {"a": 1}, "_meta": {"traceId": "abc"}}
        proto = convert.call_tool_params_dict_to_proto(d)
        self.assertTrue(proto.HasField("common"))
        self.assertTrue(proto.common.HasField("metadata"))

        back = convert.call_tool_request_proto_to_params_dict(proto)
        self.assertEqual(back["_meta"], {"traceId": "abc"})
        # Numbers in Struct become floats: a=1 -> 1.0 after Struct round-trip.
        self.assertEqual(back["arguments"], {"a": 1.0})


class CallToolResultTest(absltest.TestCase):

    def test_text_round_trip(self):
        d = {"isError": False, "content": [{"type": "text", "text": "hello"}]}
        proto = convert.call_tool_result_dict_to_proto(d)
        self.assertFalse(proto.is_error)
        self.assertEqual(proto.content[0].text.text, "hello")
        self.assertEqual(convert.call_tool_result_proto_to_dict(proto), d)

    def test_image_audio_round_trip(self):
        d = {
            "isError": False,
            "content": [
                {"type": "image", "data": "dGVzdA==", "mimeType": "image/png"},
                {"type": "audio", "data": "dGVzdA==", "mimeType": "audio/wav"},
            ],
        }
        proto = convert.call_tool_result_dict_to_proto(d)
        self.assertEqual(proto.content[0].image.data, b"dGVzdA==")
        self.assertEqual(proto.content[0].image.mime_type, "image/png")
        self.assertEqual(proto.content[1].audio.data, b"dGVzdA==")
        self.assertEqual(convert.call_tool_result_proto_to_dict(proto), d)

    def test_embedded_resource_text_round_trip(self):
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
        self.assertEqual(proto.content[0].embedded_resource.contents.text, "body")
        self.assertEqual(convert.call_tool_result_proto_to_dict(proto), d)

    def test_embedded_resource_blob_round_trip(self):
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
        self.assertEqual(proto.content[0].embedded_resource.contents.blob, b"dGVzdA==")
        self.assertEqual(convert.call_tool_result_proto_to_dict(proto), d)

    def test_resource_link_round_trip(self):
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
        self.assertEqual(proto.content[0].resource_link.uri, "x://link")
        self.assertEqual(convert.call_tool_result_proto_to_dict(proto), d)

    def test_structured_content_round_trip(self):
        d = {"isError": False, "content": [], "structuredContent": {"answer": 42}}
        proto = convert.call_tool_result_dict_to_proto(d)
        self.assertTrue(proto.HasField("structured_content"))

        back = convert.call_tool_result_proto_to_dict(proto)
        # Struct turns 42 into 42.0.
        self.assertEqual(back["structuredContent"], {"answer": 42.0})
        self.assertFalse(back["isError"])
        self.assertEqual(back["content"], [])

    def test_unknown_content_type_raises(self):
        with self.assertRaisesRegex(ValueError, "Unsupported content block type"):
            convert.call_tool_result_dict_to_proto({"content": [{"type": "alien"}]})

    def test_content_block_from_proto_raises_on_empty_oneof(self):
        empty = mcp_messages_pb2.CallToolResponse.Content()
        with self.assertRaisesRegex(ValueError, "no recognised oneof variant"):
            convert._content_block_proto_to_dict(empty)


class ResourcesTest(absltest.TestCase):

    def test_round_trip(self):
        d = {
            "resources": [
                {"uri": "x://a", "name": "a", "mimeType": "text/plain", "size": 100},
                {"uri": "x://b", "name": "b"},  # minimal
            ]
        }
        proto = convert.list_resources_result_dict_to_proto(d)
        self.assertEqual(proto.resources[0].size, 100)
        self.assertEqual(proto.resources[1].size, 0)
        self.assertEqual(convert.list_resources_result_proto_to_dict(proto), d)

    def test_omits_unset_optionals_in_dict(self):
        proto = mcp_messages_pb2.ListResourcesResponse()
        proto.resources.append(mcp_messages_pb2.Resource(uri="x://x", name="x"))
        d = convert.list_resources_result_proto_to_dict(proto)
        self.assertEqual(d, {"resources": [{"uri": "x://x", "name": "x"}]})


class ResourceTemplatesTest(absltest.TestCase):

    def test_round_trip(self):
        d = {
            "resourceTemplates": [
                {"uriTemplate": "x://{n}", "name": "t", "mimeType": "text/plain"},
                {"uriTemplate": "y://{n}", "name": "u"},
            ]
        }
        proto = convert.list_resource_templates_result_dict_to_proto(d)
        self.assertEqual(proto.resource_templates[0].uri_template, "x://{n}")
        self.assertEqual(convert.list_resource_templates_result_proto_to_dict(proto), d)


class ReadResourceTest(absltest.TestCase):

    def test_params_round_trip(self):
        d = {"uri": "x://r"}
        proto = convert.read_resource_params_dict_to_proto(d)
        self.assertEqual(proto.uri, "x://r")
        self.assertEqual(convert.read_resource_request_proto_to_params_dict(proto), d)

    def test_params_meta_round_trip(self):
        d = {"uri": "x://r", "_meta": {"trace": "t"}}
        proto = convert.read_resource_params_dict_to_proto(d)
        self.assertTrue(proto.common.HasField("metadata"))
        self.assertEqual(convert.read_resource_request_proto_to_params_dict(proto), d)

    def test_result_text_round_trip(self):
        d = {"contents": [{"uri": "x://r", "mimeType": "text/plain", "text": "hi"}]}
        proto = convert.read_resource_result_dict_to_proto(d)
        self.assertEqual(proto.resource[0].text, "hi")
        self.assertEqual(proto.resource[0].blob, b"")
        self.assertEqual(convert.read_resource_result_proto_to_dict(proto), d)

    def test_result_blob_round_trip(self):
        d = {"contents": [{"uri": "x://r", "mimeType": "application/octet-stream", "blob": "dGVzdA=="}]}
        proto = convert.read_resource_result_dict_to_proto(d)
        self.assertEqual(proto.resource[0].blob, b"dGVzdA==")
        self.assertEqual(convert.read_resource_result_proto_to_dict(proto), d)


if __name__ == "__main__":
    absltest.main()
