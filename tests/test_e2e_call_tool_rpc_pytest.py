import base64

from mcp import types as mcp_types
from pydantic.networks import AnyUrl
import pytest
import pytest_asyncio
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils


@pytest_asyncio.fixture
async def mcp_client():
  """Sets up the test server and client session for each test."""
  test_server = test_utils.TestServerWithTools()
  await test_server.start_grpc_server()

  client_session = mcp_grpc_client.GRPCClientSession(
      target=f"localhost:{test_server.port}",
  )

  yield client_session

  # Teardown
  await client_session.close()
  await grpc_server.stop_grpc_server(test_server.grpc_server, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name, args, expected_content_type, expected_content_attrs",
    [
        (
            "echo",
            {"message": "World"},
            mcp_types.TextContent,
            {"text": "Hello World"},
        ),
        ("add", {"a": 10, "b": 20}, mcp_types.TextContent, {"text": "30"}),
        (
            "tool_with_structured_output",
            {},
            mcp_types.TextContent,
            {"text": '{\n  "structured_output": "test"\n}'},
        ),
        (
            "tool_with_image_output",
            {},
            mcp_types.ImageContent,
            {
                "type": "image",
                "mimeType": "image/png",
                "data": "fake image data",
            },
        ),
        (
            "tool_with_audio_output",
            {},
            mcp_types.AudioContent,
            {
                "type": "audio",
                "mimeType": "audio/wav",
                "data": "fake audio data",
            },
        ),
        (
            "tool_with_resource_output",
            {},
            mcp_types.ResourceLink,
            {
                "type": "resource_link",
                "uri": AnyUrl("https://www.google.com/"),
                "name": "resource uri",
                "title": "Google",
                "mimeType": "text/html",
            },
        ),
    ],
)
async def test_call_tool_unstructured_content(
    mcp_client, tool_name, args, expected_content_type, expected_content_attrs
):
  """Tests the CallTool RPC with for different unstructured outputs like text, image, audio and resource link."""
  response = await mcp_client.call_tool(tool_name, args)
  assert isinstance(response, mcp_types.CallToolResult)
  assert len(response.content) == 1
  content, = response.content

  assert isinstance(content, expected_content_type)
  for attr, value in expected_content_attrs.items():
    if attr == "data":
      decoded_data = base64.b64decode(content.data).decode()
      assert decoded_data == value
    else:
      assert getattr(content, attr) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name, args, expected_structured_content",
    [
        ("echo", {"message": "World"}, {"result": "Hello World"}),
        ("add", {"a": 10, "b": 20}, {"result": 30}),
        ("tool_with_structured_output", {}, {"structured_output": "test"}),
    ],
)
async def test_structured_outputs(
    mcp_client, tool_name, args, expected_structured_content
):
  """Tests the CallTool RPC with tools that return structured outputs."""

  response = await mcp_client.call_tool(tool_name, args)
  assert isinstance(response, mcp_types.CallToolResult)
  assert response.structuredContent == expected_structured_content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name, args, expected_res_content_attrs",
    [
        (
            "tool_with_embedded_resource_text_output",
            {},
            {
                "type": mcp_types.TextResourceContents,
                "uri": AnyUrl("https://www.google.com/"),
                "text": "text content",
                "mimeType": "text/plain",
            },
        ),
        (
            "tool_with_embedded_resource_blob_output",
            {},
            {
                "type": mcp_types.BlobResourceContents,
                "uri": AnyUrl("https://www.google.com/"),
                "mimeType": "application/octet-stream",
                "blob": "blob content",
            },
        ),
    ],
)
async def test_embedded_resource_outputs(
    mcp_client, tool_name, args, expected_res_content_attrs
):
  """Tests the CallTool RPC with tools that return embedded resource outputs."""

  response = await mcp_client.call_tool(tool_name, args)
  assert isinstance(response, mcp_types.CallToolResult)
  assert len(response.content) == 1

  (content,) = response.content
  assert isinstance(content, mcp_types.EmbeddedResource)
  assert content.type == "resource"

  resource_contents = content.resource
  assert isinstance(resource_contents, expected_res_content_attrs["type"])

  for attr, value in expected_res_content_attrs.items():
    if attr == "type":
      continue
    elif attr == "blob":
      decoded_blob = base64.b64decode(resource_contents.blob).decode()
      assert decoded_blob == value
    else:
      assert getattr(resource_contents, attr) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name, args, expected_error_msgs",
    [
        ("", {}, ["Tool name cannot be empty."]),
        ("non_existent_tool", {}, ["Unknown tool: non_existent_tool"]),
        (
            "echo",
            {},
            [
                "1 validation error for echo",
                (
                    r"Arguments\nmessage\n  Field required [type=missing,"
                    r" input_value={}, input_type=dict]"
                ),
            ],
        ),
        ("invalidTool", {}, ["Error executing tool invalidTool: invalid tool"]),
        (
            "tool_with_wrong_output",
            {},
            [
                "1 validation error for tool_with_wrong_output",
                (
                    r"Output\nresult\n  Input should be a valid string"
                    r" [type=string_type, input_value=123, input_type=int]"
                ),
            ],
        ),
    ],
)
async def test_call_tool_with_error_response(
    mcp_client, tool_name, args, expected_error_msgs
):
  """Tests the CallTool RPC for cases when an error response is returned.

  This tests cases like tool not found, input/output schema mismatch,
  or tool related errors that are sent as Text response with isError=True.
  """
  response = await mcp_client.call_tool(tool_name, args)

  assert isinstance(response, mcp_types.CallToolResult)
  assert response.isError
  assert len(response.content) == 1
  content, = response.content
  error_msg = content.text

  for expected_error in expected_error_msgs:
    assert expected_error in error_msg
