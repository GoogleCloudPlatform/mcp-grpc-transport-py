import base64
import unittest

from absl.testing import absltest
from absl.testing import parameterized
from mcp import types as mcp_types
from pydantic.networks import AnyUrl

import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils


class TestCallToolRPC(parameterized.TestCase, unittest.IsolatedAsyncioTestCase):
  """Client-side test suite for call_tool implementation."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  @parameterized.named_parameters(
      dict(
          testcase_name="_Echo",
          tool_name="echo",
          args={"message": "World"},
          expected_content_type=mcp_types.TextContent,
          expected_content_attrs={"text": "Hello World"},
      ),
      dict(
          testcase_name="_Add",
          tool_name="add",
          args={"a": 10, "b": 20},
          expected_content_type=mcp_types.TextContent,
          expected_content_attrs={"text": "30"},
      ),
      dict(
          testcase_name="_StructuredOutput",
          tool_name="tool_with_structured_output",
          args={},
          expected_content_type=mcp_types.TextContent,
          expected_content_attrs={"text": '{\n  "structured_output": "test"\n}'},
      ),
      dict(
          testcase_name="_ImageOutput",
          tool_name="tool_with_image_output",
          args={},
          expected_content_type=mcp_types.ImageContent,
          expected_content_attrs={
              "type": "image",
              "mimeType": "image/png",
              "data": "fake image data",
          },
      ),
      dict(
          testcase_name="_AudioOutput",
          tool_name="tool_with_audio_output",
          args={},
          expected_content_type=mcp_types.AudioContent,
          expected_content_attrs={
              "type": "audio",
              "mimeType": "audio/wav",
              "data": "fake audio data",
          },
      ),
      dict(
          testcase_name="_ResourceOutput",
          tool_name="tool_with_resource_output",
          args={},
          expected_content_type=mcp_types.ResourceLink,
          expected_content_attrs={
              "type": "resource_link",
              "uri": AnyUrl("https://www.google.com/"),
              "name": "resource uri",
              "title": "Google",
              "mimeType": "text/html",
          },
      ),
  )
  async def test_call_tool_unstructured_content(
      self, *, tool_name, args, expected_content_type, expected_content_attrs
  ):
    """Tests the CallTool RPC with for different unstructured outputs like text, image, audio and resource link."""
    response = await self.client_session.call_tool(tool_name, args)
    self.assertIsInstance(response, mcp_types.CallToolResult)
    self.assertLen(response.content, 1)
    content, = response.content

    self.assertIsInstance(content, expected_content_type)
    for attr, value in expected_content_attrs.items():
      if attr == "data":
        decoded_data = base64.b64decode(content.data).decode()
        self.assertEqual(decoded_data, value)
      else:
        self.assertEqual(getattr(content, attr), value)

  @parameterized.named_parameters(
      dict(
          testcase_name="_Echo",
          tool_name="echo",
          args={"message": "World"},
          expected_structured_content={"result": "Hello World"},
      ),
      dict(
          testcase_name="_Add",
          tool_name="add",
          args={"a": 10, "b": 20},
          expected_structured_content={"result": 30},
      ),
      dict(
          testcase_name="_StructuredOutput",
          tool_name="tool_with_structured_output",
          args={},
          expected_structured_content={"structured_output": "test"},
      ),
  )
  async def test_structured_outputs(
      self, *, tool_name, args, expected_structured_content
  ):
    """Tests the CallTool RPC with tools that return structured outputs."""

    response = await self.client_session.call_tool(tool_name, args)
    self.assertIsInstance(response, mcp_types.CallToolResult)
    self.assertEqual(response.structuredContent, expected_structured_content)

  @parameterized.named_parameters(
      dict(
          testcase_name="_TextOutput",
          tool_name="tool_with_embedded_resource_text_output",
          args={},
          expected_res_content_attrs={
              "type": mcp_types.TextResourceContents,
              "uri": AnyUrl("https://www.google.com/"),
              "text": "text content",
              "mimeType": "text/plain",
          },
      ),
      dict(
          testcase_name="_BlobOutput",
          tool_name="tool_with_embedded_resource_blob_output",
          args={},
          expected_res_content_attrs={
              "type": mcp_types.BlobResourceContents,
              "uri": AnyUrl("https://www.google.com/"),
              "mimeType": "application/octet-stream",
              "blob": "blob content",
          },
      ),
  )
  async def test_embedded_resource_outputs(
      self, *, tool_name, args, expected_res_content_attrs
  ):
    """Tests the CallTool RPC with tools that return embedded resource outputs."""

    response = await self.client_session.call_tool(tool_name, args)
    self.assertIsInstance(response, mcp_types.CallToolResult)
    self.assertLen(response.content, 1)

    (content,) = response.content
    self.assertIsInstance(content, mcp_types.EmbeddedResource)
    self.assertEqual(content.type, "resource")

    resource_contents = content.resource
    self.assertIsInstance(resource_contents, expected_res_content_attrs["type"])

    for attr, value in expected_res_content_attrs.items():
      if attr == "type":
        continue
      elif attr == "blob":
        decoded_blob = base64.b64decode(resource_contents.blob).decode()
        self.assertEqual(decoded_blob, value)
      else:
        self.assertEqual(getattr(resource_contents, attr), value)

  @parameterized.named_parameters(
      dict(
          testcase_name="_EmptyToolName",
          tool_name="",
          args={},
          expected_error_msgs=["Tool name cannot be empty."],
      ),
      dict(
          testcase_name="_NonExistentTool",
          tool_name="non_existent_tool",
          args={},
          expected_error_msgs=["Unknown tool: non_existent_tool"],
      ),
      dict(
          testcase_name="_MissingArguments",
          tool_name="echo",
          args={},
          expected_error_msgs=[
              "1 validation error for echo",
              (
                  r"Arguments\nmessage\n  Field required [type=missing,"
                  r" input_value={}, input_type=dict]"
              ),
          ],
      ),
      dict(
          testcase_name="_InvalidTool",
          tool_name="invalidTool",
          args={},
          expected_error_msgs=["Error executing tool invalidTool: invalid tool"],
      ),
      dict(
          testcase_name="_WrongOutput",
          tool_name="tool_with_wrong_output",
          args={},
          expected_error_msgs=[
              "1 validation error for tool_with_wrong_output",
              (
                  r"Output\nresult\n  Input should be a valid string"
                  r" [type=string_type, input_value=123, input_type=int]"
              ),
          ],
      ),
  )
  async def test_call_tool_with_error_response(
      self, *, tool_name, args, expected_error_msgs
  ):
    """Tests the CallTool RPC for cases when an error response is returned.

    This tests cases like tool not found, input/output schema mismatch,
    or tool related errors that are sent as Text response with isError=True.
    """
    response = await self.client_session.call_tool(tool_name, args)

    self.assertIsInstance(response, mcp_types.CallToolResult)
    self.assertTrue(response.isError)
    self.assertLen(response.content, 1)
    content, = response.content
    error_msg = content.text

    for expected_error in expected_error_msgs:
      self.assertIn(expected_error, error_msg)


if __name__ == "__main__":
  absltest.main()
