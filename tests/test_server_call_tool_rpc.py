import asyncio
import base64
import unittest

from mcp_grpc_transport.server import grpc_server
from tests import test_utils

from google.protobuf import struct_pb2
from google3.testing.pybase import googletest
from google3.testing.pybase import parameterized
from mcp_grpc_transport_proto import mcp_messages_pb2


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
        request=mcp_messages_pb2.CallToolRequest.Request(name=tool_name, arguments=args)
    )

    return await self.test_client.stub.CallTool(request, metadata=metadata)

  async def test_call_tool(self):
    """Tests the CallTool RPC with text content."""

    args = struct_pb2.Struct()
    args.update({"message": "World"})

    response = await self._make_tool_call("echo", args)

    found_content = False
    if response.content:
      for content in response.content:
        if content.text.text == "Hello World":
          found_content = True

    self.assertTrue(
        found_content, "Did not find expected response 'Hello World'"
    )

  async def test_call_tool_structured(self):
    """Tests the CallTool RPC with structured response content."""

    args = struct_pb2.Struct()
    args.update({"a": 10, "b": 20})

    response = await self._make_tool_call("add", args)

    # Check structured_content
    found_result = False
    if response.HasField("structured_content"):
      # FastMCP returns {'result': 30} for add(10, 20)
      if response.structured_content["result"] == 30:
        found_result = True

    self.assertTrue(found_result, "Did not find expected structured result 30")

  async def test_call_tool_with_image_output(self):
    """Tests the CallTool RPC with image output."""
    args = struct_pb2.Struct()
    response = await self._make_tool_call("tool_with_image_output", args)

    self.assertEqual(len(response.content), 1)

    content = response.content[0]
    self.assertTrue(content.HasField("image"))

    with self.subTest(name="VerifyImageContent"):
      self.assertEqual(content.image.mime_type, "image/png")
      self.assertEqual(base64.b64decode(content.image.data), b"fake image data")

  async def test_call_tool_with_audio_output(self):
    """Tests the CallTool RPC with audio output."""
    args = struct_pb2.Struct()
    response = await self._make_tool_call("tool_with_audio_output", args)

    self.assertEqual(len(response.content), 1)

    content = response.content[0]
    self.assertTrue(content.HasField("audio"))

    with self.subTest(name="VerifyAudioContent"):
      self.assertEqual(content.audio.mime_type, "audio/wav")
      self.assertEqual(base64.b64decode(content.audio.data), b"fake audio data")

  async def test_call_tool_with_resource_output(self):
    """Tests the CallTool RPC with resource output."""
    args = struct_pb2.Struct()
    response = await self._make_tool_call("tool_with_resource_output", args)

    self.assertEqual(len(response.content), 1)
    self.assertTrue(response.content[0].HasField("resource_link"))

    resource_link = response.content[0].resource_link

    self.assertEqual(resource_link.uri, "https://www.google.com/")
    self.assertEqual(resource_link.name, "resource uri")
    self.assertEqual(resource_link.title, "Google")
    self.assertEqual(resource_link.mime_type, "text/html")

  async def test_call_tool_with_embedded_resource_text_output(self):
    """Tests the CallTool RPC with embedded resource text output."""
    args = struct_pb2.Struct()
    response = await self._make_tool_call(
        "tool_with_embedded_resource_text_output", args
    )

    self.assertEqual(len(response.content), 1)
    self.assertTrue(response.content[0].HasField("embedded_resource"))
    self.assertTrue(response.content[0].embedded_resource.HasField("contents"))

    contents = response.content[0].embedded_resource.contents
    self.assertEqual(contents.uri, "https://www.google.com/")
    self.assertEqual(contents.text, "text content")
    self.assertEqual(contents.mime_type, "text/plain")

  async def test_call_tool_with_embedded_resource_blob_output(self):
    """Tests the CallTool RPC with embedded resource blob output."""
    args = struct_pb2.Struct()
    response = await self._make_tool_call(
        "tool_with_embedded_resource_blob_output", args
    )

    self.assertEqual(len(response.content), 1)
    self.assertTrue(response.content[0].HasField("embedded_resource"))
    self.assertTrue(response.content[0].embedded_resource.HasField("contents"))

    contents = response.content[0].embedded_resource.contents
    self.assertEqual(contents.uri, "https://www.google.com/")
    self.assertEqual(base64.b64decode(contents.blob), b"blob content")
    self.assertEqual(contents.mime_type, "application/octet-stream")

  async def test_call_tool_with_structured_output(self):
    """Tests the CallTool RPC with a structured output."""
    args = struct_pb2.Struct()
    response = await self._make_tool_call("tool_with_structured_output", args)

    self.assertTrue(response.HasField("structured_content"))
    structured_content = response.structured_content
    self.assertIsInstance(structured_content, struct_pb2.Struct)

    self.assertEqual(structured_content["structured_output"], "test")

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
  googletest.main()
