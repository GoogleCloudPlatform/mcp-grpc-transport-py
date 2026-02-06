import asyncio
import unittest

from mcp_grpc_transport.server import grpc_server
from tests import test_utils

from google.protobuf import struct_pb2
from google3.testing.pybase import googletest
from mcp_grpc_transport_proto import mcp_pb2


class TestCallToolRPC(unittest.IsolatedAsyncioTestCase):
  """Tests the different RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()

    await self.test_server.start_grpc_server()

    self.test_client = test_utils.TestServerClient(
        self.test_server.port
    )

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def _make_tool_call(
      self, tool_name: str, args: struct_pb2.Struct,
      metadata: list[tuple[str, str]] | None = None,
  ) -> list[mcp_pb2.CallToolResponse]:
    """Makes a tool call and returns the responses as a list.

    Args:
      tool_name: The name of the tool to call.
      args: The arguments to pass to the tool.
      metadata: The metadata to pass to the RPC. If None, the default metadata
        with a supported MCP version is used.

    Returns:
      A list of CallToolResponse objects.
    """
    if metadata is None:
      metadata = self.test_server.version_metadata

    request = mcp_pb2.CallToolRequest(
        request=mcp_pb2.CallToolRequest.Request(name=tool_name, arguments=args)
    )

    responses = [response async for response in self.test_client.stub.CallTool(
        request, metadata=metadata
    )]

    return responses

  async def test_call_tool(self):
    """Tests the CallTool RPC with text content."""

    args = struct_pb2.Struct()
    args.update({"message": "World"})

    responses = await self._make_tool_call("echo", args)

    self.assertGreater(len(responses), 0)

    found_content = False
    for response in responses:
      if not response.content:
        continue

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

    responses = await self._make_tool_call("add", args)

    self.assertGreater(len(responses), 0)

    # Check structured_content
    found_result = False
    for response in responses:
      if response.HasField("structured_content"):
        # FastMCP returns {'result': 30} for add(10, 20)
        if response.structured_content["result"] == 30:
          found_result = True

    self.assertTrue(found_result, "Did not find expected structured result 30")

  async def test_call_tool_with_progress(self):
    """Tests the CallTool RPC with progress updates."""

    args = struct_pb2.Struct()
    # Small size to make test fast, but enough for a few chunks
    # 0.2 MB = 204.8 KB. Chunk 64KB. ~4 chunks.
    args.update({"filename": "test.txt", "size_mb": 0.2})

    request = mcp_pb2.CallToolRequest(
        common=mcp_pb2.RequestFields(
            progress=mcp_pb2.ProgressNotification(progress_token="test-token")
        ),
        request=mcp_pb2.CallToolRequest.Request(
            name="download_file", arguments=args
        ),
    )

    responses = []
    progress_updates = []
    final_result = None

    async for response in self.test_client.stub.CallTool(
        request, metadata=self.test_server.version_metadata
    ):
      responses.append(response)
      if response.common.HasField("progress"):
        progress_updates.append(response.common.progress)

      if response.content:
        for content in response.content:
          final_result = content.text.text

    with self.subTest(name="VerifyProgressUpdates"):
      # We're using a small file size (0.2 MB) for this test.
      # 0.2 MB = 204.8 KB. Chunk size = 64KB. ~4 chunks.
      # Hence, expect 4 progress updates.
      self.assertEqual(
          len(progress_updates), 4, "No progress updates received"
      )

    with self.subTest(name="VerifyFinalResult"):
      self.assertEqual(final_result, "Successfully downloaded test.txt")

  async def test_call_tool_with_image_output(self):
    """Tests the CallTool RPC with image output."""
    args = struct_pb2.Struct()
    responses = await self._make_tool_call("tool_with_image_output", args)

    self.assertEqual(len(responses), 1)
    response = responses[0]

    self.assertEqual(len(response.content), 1)
    self.assertTrue(response.content[0].HasField("image"))

    self.assertEqual(response.content[0].image.mime_type, "image/png")
    self.assertEqual(response.content[0].image.data, b"fake image data")

  async def test_call_tool_with_audio_output(self):
    """Tests the CallTool RPC with audio output."""
    args = struct_pb2.Struct()
    responses = await self._make_tool_call("tool_with_audio_output", args)

    self.assertEqual(len(responses), 1)
    response = responses[0]

    self.assertEqual(len(response.content), 1)
    self.assertTrue(response.content[0].HasField("audio"))

    self.assertEqual(response.content[0].audio.mime_type, "audio/wav")
    self.assertEqual(response.content[0].audio.data, b"fake audio data")

  async def test_call_tool_with_resource_output(self):
    """Tests the CallTool RPC with resource output."""
    args = struct_pb2.Struct()
    responses = await self._make_tool_call("tool_with_resource_output", args)

    self.assertEqual(len(responses), 1)
    response = responses[0]

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
    responses = await self._make_tool_call(
        "tool_with_embedded_resource_text_output", args
    )

    self.assertEqual(len(responses), 1)
    response = responses[0]

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
    responses = await self._make_tool_call(
        "tool_with_embedded_resource_blob_output", args
    )

    self.assertEqual(len(responses), 1)
    response = responses[0]

    self.assertEqual(len(response.content), 1)
    self.assertTrue(response.content[0].HasField("embedded_resource"))
    self.assertTrue(response.content[0].embedded_resource.HasField("contents"))

    contents = response.content[0].embedded_resource.contents
    self.assertEqual(contents.uri, "https://www.google.com/")
    self.assertEqual(contents.blob, b"blob content")
    self.assertEqual(contents.mime_type, "application/octet-stream")

  async def test_call_tool_with_structured_output(self):
    """Tests the CallTool RPC with a structured output."""
    args = struct_pb2.Struct()
    responses = await self._make_tool_call(
        "tool_with_structured_output", args
    )

    self.assertEqual(len(responses), 1)
    response = responses[0]

    self.assertTrue(response.HasField("structured_content"))
    structured_content = response.structured_content
    self.assertIsInstance(structured_content, struct_pb2.Struct)

    self.assertEqual(structured_content["structured_output"], "test")

  async def test_call_tool_cancellation(self):
    """Tests CallTool RPC cancellation."""
    args = struct_pb2.Struct()
    args.update({"filename": "test.txt", "size_mb": 1})

    request = mcp_pb2.CallToolRequest(
        common=mcp_pb2.RequestFields(
            progress=mcp_pb2.ProgressNotification(progress_token="test-token")
        ),
        request=mcp_pb2.CallToolRequest.Request(
            name="download_file", arguments=args
        ),
    )

    call = self.test_client.stub.CallTool(
        request, metadata=self.test_server.version_metadata
    )

    responses = []
    try:
      async for response in call:
        responses.append(response)
        # Cancel after receiving the first message
        call.cancel()
    except asyncio.CancelledError:
      self.assertTrue(call.cancelled())
    else:
      self.fail("asyncio.CancelledError not raised on cancellation.")

  async def test_call_tool_with_no_tool_name(self):
    """Tests CallTool RPC with no tool name."""
    args = struct_pb2.Struct()
    args.update({"message": "World"})

    responses = await self._make_tool_call("", args)

    self.assertEqual(len(responses), 1)
    response = responses[0]
    self.assertIsInstance(response, mcp_pb2.CallToolResponse)

    self.assertTrue(response.is_error)

    contents = response.content

    for content in contents:
      if content.HasField("text"):
        error_msg = content.text.text
        self.assertIn("Tool name cannot be empty.", error_msg)
        break
    else:
      self.fail("No error text content found in the response.")

  async def test_call_tool_wrong_args(self):
    """Tests the CallTool RPC with wrong arguments."""

    args = struct_pb2.Struct()
    tool_name = "echo"
    responses = await self._make_tool_call(tool_name, args)

    self.assertEqual(len(responses), 1)
    response = responses[0]
    self.assertIsInstance(response, mcp_pb2.CallToolResponse)

    self.assertTrue(response.is_error)

    contents = response.content

    for content in contents:
      if content.HasField("text"):
        error_msg = content.text.text

        self.assertIn(f"1 validation error for {tool_name}", error_msg)
        self.assertIn(
            "Arguments\\nmessage\\n  Field required [type=missing,"
            " input_value={}, input_type=dict]",
            error_msg,
        )
        break
    else:
      self.fail("No error text content found in the response.")

  async def test_call_tool_that_raises_exception(self):
    """Tests the CallTool RPC with a tool that raises an exception."""
    args = struct_pb2.Struct()
    responses = await self._make_tool_call("invalidTool", args)

    self.assertEqual(len(responses), 1)
    response = responses[0]
    self.assertIsInstance(response, mcp_pb2.CallToolResponse)

    self.assertTrue(response.is_error)

    contents = response.content

    for content in contents:
      if content.HasField("text"):
        error_msg = content.text.text
        self.assertIn(
            "Error executing tool invalidTool: invalid tool", error_msg
        )
        break
    else:
      self.fail("No error text content found in the response.")

  async def test_call_tool_with_wrong_output(self):
    """Tests the CallTool RPC with a tool that returns wrong output."""
    args = struct_pb2.Struct()
    tool_name = "tool_with_wrong_output"

    responses = await self._make_tool_call(tool_name, args)

    self.assertEqual(len(responses), 1)
    response = responses[0]
    self.assertIsInstance(response, mcp_pb2.CallToolResponse)

    self.assertTrue(response.is_error)

    contents = response.content

    for content in contents:
      if content.HasField("text"):
        error_msg = content.text.text
        self.assertIn(f"1 validation error for {tool_name}", error_msg)
        self.assertIn(
            "Output\\nresult\\n  Input should be a valid string "
            "[type=string_type, input_value=123, input_type=int]",
            error_msg,
        )
        break
    else:
      self.fail("No error text content found in the response.")

if __name__ == "__main__":
  googletest.main()
