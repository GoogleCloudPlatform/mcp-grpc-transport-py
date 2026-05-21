import asyncio
import base64
import unittest

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import struct_pb2
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport.server import grpc_server
from tests import test_utils


class TestCallToolRPC(parameterized.TestCase, unittest.IsolatedAsyncioTestCase):
  """Tests the different RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()

    await self.test_server.start_grpc_server()

    self.test_client = test_utils.FakeTestClient(
        self.test_server.port
    )

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def _make_tool_call(
      self,
      tool_name: str,
      args: struct_pb2.Struct,
      metadata: list[tuple[str, str]] | None = None,
  ) -> mcp_messages_pb2.CallToolResponse:
    """Makes a tool call and returns the response.

    Args:
      tool_name: The name of the tool to call.
      args: The arguments to pass to the tool.
      metadata: The metadata to pass to the RPC. If None, the default metadata
        with a supported MCP version is used.

    Returns:
      A CallToolResponse object.
    """
    if metadata is None:
      metadata = self.test_server.version_metadata

    request = mcp_messages_pb2.CallToolRequest(
        request=mcp_messages_pb2.CallToolRequest.Request(
            name=tool_name, arguments=args
        )
    )

    return await self.test_client.stub.CallTool(request, metadata=metadata)

  @parameterized.named_parameters(
      dict(
          testcase_name="_text_content",
          tool_name="echo",
          args={"message": "World"},
          expected_content_proto=[
              mcp_messages_pb2.CallToolResponse.Content(
                  text=mcp_messages_pb2.TextContent(text="Hello World")
              )
          ],
      ),
      dict(
          testcase_name="_image_content",
          tool_name="tool_with_image_output",
          args={},
          expected_content_proto=[
              mcp_messages_pb2.CallToolResponse.Content(
                  image=mcp_messages_pb2.ImageContent(
                      data=base64.b64encode(b"fake image data"),
                      mime_type="image/png",
                  )
              )
          ],
      ),
      dict(
          testcase_name="_audio_content",
          tool_name="tool_with_audio_output",
          args={},
          expected_content_proto=[
              mcp_messages_pb2.CallToolResponse.Content(
                  audio=mcp_messages_pb2.AudioContent(
                      data=base64.b64encode(b"fake audio data"),
                      mime_type="audio/wav",
                  )
              )
          ],
      ),
      dict(
          testcase_name="_resource_content",
          tool_name="tool_with_resource_output",
          args={},
          expected_content_proto=[
              mcp_messages_pb2.CallToolResponse.Content(
                  resource_link=mcp_messages_pb2.Resource(
                      uri="https://www.google.com/",
                      name="resource uri",
                      title="Google",
                      mime_type="text/html",
                  )
              )
          ],
      ),
      dict(
          testcase_name="_embedded_resource_text_content",
          tool_name="tool_with_embedded_resource_text_output",
          args={},
          expected_content_proto=[
              mcp_messages_pb2.CallToolResponse.Content(
                  embedded_resource=mcp_messages_pb2.EmbeddedResource(
                      contents=mcp_messages_pb2.ResourceContents(
                          uri="https://www.google.com/",
                          text="text content",
                          mime_type="text/plain",
                      )
                  )
              )
          ],
      ),
      dict(
          testcase_name="_embedded_resource_blob_content",
          tool_name="tool_with_embedded_resource_blob_output",
          args={},
          expected_content_proto=[
              mcp_messages_pb2.CallToolResponse.Content(
                  embedded_resource=mcp_messages_pb2.EmbeddedResource(
                      contents=mcp_messages_pb2.ResourceContents(
                          uri="https://www.google.com/",
                          blob=base64.b64encode(b"blob content"),
                          mime_type="application/octet-stream",
                      )
                  )
              )
          ],
      ),
  )
  async def test_call_tool(self, tool_name, args, expected_content_proto):
    """Tests the CallTool RPC with various content types."""

    args_proto = struct_pb2.Struct()
    args_proto.update(args)

    response = await self._make_tool_call(tool_name, args_proto)

    self.assertEqual(
        response.content,
        expected_content_proto,
        "Actual response does not match the expected response.",
    )

  @parameterized.named_parameters(
      dict(
          testcase_name="_add",
          tool_name="add",
          args={"a": 10, "b": 20},
          expected_structured_content={"result": 30.0},
      ),
      dict(
          testcase_name="_dict",
          tool_name="tool_with_structured_output",
          args={},
          expected_structured_content={"structured_output": "test"},
      ),
  )
  async def test_call_tool_structured_output(
      self, tool_name, args, expected_structured_content
  ):
    """Tests the CallTool RPC with structured response content."""

    args_proto = struct_pb2.Struct()
    args_proto.update(args)

    response = await self._make_tool_call(tool_name, args_proto)

    expected_structured_content_proto = struct_pb2.Struct()
    expected_structured_content_proto.update(expected_structured_content)

    self.assertEqual(
        response.structured_content,
        expected_structured_content_proto,
        "Actual structured response does not match the expected response.",
    )

  async def test_call_tool_cancellation(self):
    """Tests CallTool RPC cancellation."""
    args = struct_pb2.Struct()
    args.update({"filename": "test.txt", "size_mb": 1})

    request = mcp_messages_pb2.CallToolRequest(
        common=mcp_messages_pb2.RequestFields(),
        request=mcp_messages_pb2.CallToolRequest.Request(
            name="download_file", arguments=args
        ),
    )

    call = self.test_client.stub.CallTool(
        request, metadata=self.test_server.version_metadata
    )

    # Cancel the call immediately
    call.cancel()

    with self.assertRaises(asyncio.CancelledError):
      await call

  @parameterized.named_parameters(
      dict(
          testcase_name="_no_tool_name",
          tool_name="",
          args=struct_pb2.Struct(),
          expected_error_msgs=[
              "Tool name cannot be empty.",
          ],
      ),
      dict(
          testcase_name="_non_existent_tool",
          tool_name="non_existent_tool",
          args=struct_pb2.Struct(),
          expected_error_msgs=[
              "Unknown tool: non_existent_tool",
          ],
      ),
      dict(
          testcase_name="_wrong_args",
          tool_name="echo",
          args=struct_pb2.Struct(),
          expected_error_msgs=[
              "1 validation error for echo",
              "Arguments\\nmessage\\n  Field required [type=missing,"
              + " input_value={}, input_type=dict]",
          ],
      ),
      dict(
          testcase_name="_tool_raises_exception",
          tool_name="invalidTool",
          args=struct_pb2.Struct(),
          expected_error_msgs=[
              "Error executing tool invalidTool: invalid tool",
          ],
      ),
      dict(
          testcase_name="_wrong_output",
          tool_name="tool_with_wrong_output",
          args=struct_pb2.Struct(),
          expected_error_msgs=[
              "1 validation error for tool_with_wrong_output",
              "Output\\nresult\\n  Input should be a valid string "
              + "[type=string_type, input_value=123, input_type=int]",
          ],
      ),
  )
  async def test_call_tool_error_case(
      self, tool_name, args, expected_error_msgs
  ):
    """Tests CallTool RPC error cases."""

    response = await self._make_tool_call(tool_name, args)
    self.assertIsInstance(response, mcp_messages_pb2.CallToolResponse)

    self.assertTrue(response.is_error)

    contents = response.content

    self.assertLen(contents, 1)
    (content,) = contents

    self.assertTrue(
        content.HasField("text"), "No error text content found in the response."
    )
    error_msg = content.text.text
    for expected_error_msg in expected_error_msgs:
      self.assertIn(expected_error_msg, error_msg)


if __name__ == "__main__":
  absltest.main()
