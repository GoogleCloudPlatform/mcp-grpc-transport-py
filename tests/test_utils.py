"""Utility functions and classes for testing."""

import base64
from collections.abc import Sequence
from google.protobuf import json_format
import grpc
import socket
from contextlib import closing
import pathlib
from typing import Any

import anyio
from mcp import types as mcp_types
from mcp.server import fastmcp
from mcp_grpc_transport.server import grpc_server as grpc_server_lib
from google.protobuf import struct_pb2
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc
from mcp_grpc_transport.utils import convert_types
from mcp_grpc_transport.utils import version_utils
from pydantic import AnyUrl


def find_free_port():
  """Finds a free port."""
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
    s.bind(("localhost", 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return s.getsockname()[1]


async def run_server_for_test(mcp_grpc_server):
  async with anyio.create_task_group() as tg:
    tg.start_soon(mcp_grpc_server.run_grpc_async)
    await anyio.sleep(0.2)
    await mcp_grpc_server.stop_grpc_server(0.5)


class TestServerWithTools:
  """A test server with tools that can be used for testing ListTools and CallTool RPCs.

  The test server has the following tools:
    - add: Adds two numbers.
    - echo: Echoes back a message.
    - download_file: Simulates downloading a file with progress updates.
    - tool_with_image_output: Used for testing image content response.
    - tool_with_audio_output: Used for testing audio content response.
    - tool_with_resource_output: Used for testing resource link response.
    - tool_with_embedded_resource_text_output: Used for testing response of an
        embedded resource with text content.
    - tool_with_embedded_resource_blob_output: Used for testing response of an
        embedded resource with blob content.
    - tool_with_structured_output: Used for testing response of a structured
        dict output.
    - invalidTool: Raises an exception.
    - tool_with_wrong_output: Used for testing response of a value that does
        not match the output schema.

  The last 2 tools are used for testing error handling for CallTool RPC.
  """
  __test__ = False  # Tells pytest this is not a test class

  def __init__(self):
    # Create a FastMCP Server instance
    self.mcp_server = fastmcp.FastMCP("TestServer")
    self.version_metadata = [(
        version_utils.MCP_PROTOCOL_VERSION_KEY,
        mcp_types.LATEST_PROTOCOL_VERSION,
    )]

    # Register tools
    @self.mcp_server.tool(name="add")
    def add(a: int, b: int) -> int:
      """Add two numbers."""
      return a + b

    @self.mcp_server.tool(name="echo")
    def echo(message: str) -> str:
      """Echo back a message."""
      return "Hello " + message

    @self.mcp_server.tool(name="tool_with_image_output")
    def tool_with_image_output() -> mcp_types.ImageContent:
      """Test tool that returns an image."""
      image_data = base64.b64encode(b"fake image data").decode()
      return mcp_types.ImageContent(
          type="image",
          data=image_data,
          mimeType="image/png",
      )

    @self.mcp_server.tool(name="tool_with_audio_output")
    def tool_with_audio_output() -> mcp_types.AudioContent:
      """Test tool that returns an image."""
      audio_data = base64.b64encode(b"fake audio data").decode()
      return mcp_types.AudioContent(
          type="audio",
          data=audio_data,
          mimeType="audio/wav",
      )

    @self.mcp_server.tool(name="tool_with_resource_output")
    def tool_with_resource_output() -> mcp_types.ResourceLink:
      """Test tool that returns a resource link."""
      return mcp_types.ResourceLink(
          uri=AnyUrl("https://www.google.com"),
          type="resource_link",
          name="resource uri",
          title="Google",
          mimeType="text/html",
      )

    @self.mcp_server.tool(name="tool_with_embedded_resource_text_output")
    def tool_with_embedded_resource_text_output() -> mcp_types.EmbeddedResource:
      """Test tool that returns an embedded resource with text content."""
      return mcp_types.EmbeddedResource(
          type="resource",
          resource=mcp_types.TextResourceContents(
              uri=AnyUrl("https://www.google.com"),
              text="text content",
              mimeType="text/plain",
          ),
      )

    @self.mcp_server.tool(name="tool_with_embedded_resource_blob_output")
    def tool_with_embedded_resource_blob_output() -> mcp_types.EmbeddedResource:
      """Test tool that returns an embedded resource with blob content."""
      return mcp_types.EmbeddedResource(
          type="resource",
          resource=mcp_types.BlobResourceContents(
              uri=AnyUrl("https://www.google.com"),
              blob=base64.b64encode(b"blob content").decode(),
              mimeType="application/octet-stream",
          ),
      )

    @self.mcp_server.tool(name="tool_with_structured_output")
    def tool_with_structured_output() -> dict[str, Any]:
      """Test tool that returns a structured output."""
      return {"structured_output": "test"}

    @self.mcp_server.tool(name="invalidTool")
    def tool_that_raises() -> None:
      """This tool is expected to raise an exception."""
      raise ValueError("invalid tool")

    @self.mcp_server.tool(name="tool_with_wrong_output")
    def tool_with_wrong_output() -> str:
      """This tool intentionally returns a value that does not match the output schema."""
      return 123

    # Number of tools registered with the server.
    # This is used to verify the ListTools RPC response.
    # TODO(developer): Update this if you add/remove tools above.
    self.num_tools = 10

    # Create the servicer
    self.port = None
    self.grpc_server = None

  async def start_grpc_server(self):
    self.port = find_free_port()
    self.grpc_server = await grpc_server_lib.create_mcp_grpc_server(
        self.mcp_server, f"localhost:{self.port}"
    )


class TestServerWithResources:
  """A test server with resources used for testing RPCs related to resources."""

  __test__ = False  # Tells pytest this is not a test class

  def __init__(self):
    # Create a FastMCP Server instance
    self.mcp_server = fastmcp.FastMCP("TestServer")
    self.version_metadata = [(
        version_utils.MCP_PROTOCOL_VERSION_KEY,
        mcp_types.LATEST_PROTOCOL_VERSION,
    )]

    self.test_resources_dir = pathlib.Path(
        "google3/third_party/py/mcp_grpc_transport/tests/test_resources"
    )

    # Register resources
    @self.mcp_server.resource("test://data")
    def test_resource() -> str:
      """A test resource."""
      return "resource data"

    @self.mcp_server.resource(
        "test://binary_resource", mime_type="application/octet-stream",
    )
    def binary_resource() -> bytes:
      """A binary resource."""
      return b"binary data"

    @self.mcp_server.resource("test://empty_resource", mime_type="text/plain")
    def empty_resource() -> str:
      """An empty resource."""
      return ""

    @self.mcp_server.resource("test://template/{name}", mime_type="text/plain")
    def template_resource(name: str) -> str:
      """A template resource."""
      return f"Hello, {name}!"

    @self.mcp_server.resource(
        "test://large_text_resource", mime_type="text/plain",
    )
    def large_text_resource() -> str:
      """A large text resource of size 5MB."""
      return "a" * (5 * 1024 * 1024)

    # Number of resources registered with the server.
    # This is used to verify the ListResources and ListResourceTemplates RPC
    # responses.
    # TODO: Update this if you add/remove resources above.
    self.num_resources = 4
    self.num_resource_templates = 1

    # Create the servicer
    self.port = None
    self.grpc_server = None

  async def start_grpc_server(self):
    self.port = find_free_port()
    self.grpc_server = await grpc_server_lib.create_mcp_grpc_server(
        self.mcp_server, f"localhost:{self.port}"
    )


class FakeServicer(mcp_pb2_grpc.McpServicer):
  """A fake test servicer that implements the McpServicer interface.

  This servicer returns dummy responses for RPCs to test the mcp grpc client.
  """

  async def CallTool(self, request, context):
    await version_utils.verify_protocol_version_from_metadata(context)
    return mcp_messages_pb2.CallToolResponse(
        content=[],
        structured_content=json_format.ParseDict(
            {"test": "test"}, struct_pb2.Struct()
        )
    )

  async def ListTools(self, request, context):
    await version_utils.verify_protocol_version_from_metadata(context)
    dummy_tool = mcp_messages_pb2.Tool(
        name="test_tool",
        title="Test Tool",
        description="Test Tool",
        input_schema=json_format.ParseDict(
            {
                "type": "object",
                "properties": {"test": {"type": "string"}},
            },
            struct_pb2.Struct(),
        ),
    )

    return mcp_messages_pb2.ListToolsResponse(
        tools=[dummy_tool]
    )

  async def ListResources(self, request, context):
    await version_utils.verify_protocol_version_from_metadata(context)
    dummy_resource = mcp_messages_pb2.Resource(
        uri="test://data",
        name="Test Resource",
        title="Test Resource",
        mime_type="text/plain",
    )

    return mcp_messages_pb2.ListResourcesResponse(
        resources=[dummy_resource]
    )

  async def ListResourceTemplates(self, request, context):
    await version_utils.verify_protocol_version_from_metadata(context)
    dummy_resource_template = mcp_messages_pb2.ResourceTemplate(
        uri_template="test://{name}",
        name="Test Resource Template",
        description="Test Resource Template",
        mime_type="text/plain",
    )

    return mcp_messages_pb2.ListResourceTemplatesResponse(
        resource_templates=[dummy_resource_template]
    )

  async def ReadResource(self, request, context):
    await version_utils.verify_protocol_version_from_metadata(context)
    uri = request.uri

    # Overload the response based on the uri.
    # If uri is test://data, send a dummy resource response.
    # otherwise, send a dummy resource template response.
    if uri == "test://data":
      dummy_resource_contents = mcp_messages_pb2.ResourceContents(
          uri="test://data",
          text="resource data",
          mime_type="text/plain",
      )
    else:
      dummy_resource_contents = mcp_messages_pb2.ResourceContents(
          uri=uri,
          text="Hello World!",
          mime_type="text/plain",
      )

    return mcp_messages_pb2.ReadResourceResponse(
        resource=[dummy_resource_contents]
    )


class FakeErrorServicer(mcp_pb2_grpc.McpServicer):
  """A fake servicer that implements McpServicer interface and returns errors.

  Used to test error handling in the mcp grpc client.
  """

  async def CallTool(self, request, context):
    call_tool_params = convert_types.call_tool_params_from_proto(
        request
    )
    arguments = call_tool_params.arguments
    if arguments.get("send_error", "false") == "true":
      error_content = mcp_messages_pb2.CallToolResponse.Content(
          text=mcp_messages_pb2.TextContent(
              text="Fake error response from CallTool",
          ),
      )
      return mcp_messages_pb2.CallToolResponse(
          content=[error_content],
          is_error=True,
      )

    await context.abort(grpc.StatusCode.INTERNAL, "Fake error during CallTool")

  async def ListTools(self, request, context):
    await context.abort(grpc.StatusCode.INTERNAL, "Fake error during ListTools")

  async def ListResources(self, request, context):
    await context.abort(
        grpc.StatusCode.INTERNAL, "Fake error during ListResources"
    )

  async def ListResourceTemplates(self, request, context):
    await context.abort(
        grpc.StatusCode.INTERNAL, "Fake error during ListResourceTemplates"
    )

  async def ReadResource(self, request, context):
    if request.uri == "test://unknown_resource":
      await context.abort(
          grpc.StatusCode.NOT_FOUND, "Resource not found"
      )
    else:
      await context.abort(
          grpc.StatusCode.INTERNAL, "Fake error during ReadResource"
      )


class FakeTestServer:
  """A fake test server that implements a fake McpServicer interface.

  The server returns dummy responses for RPCs to test the mcp grpc client.
  """

  def __init__(self, test_for_error: bool = False):
    self.test_for_error = test_for_error
    self.port = find_free_port()
    self.grpc_server = None

  async def start_grpc_server(self):
    """Starts the gRPC server on a free port.

    If test_for_error is True, the server will return errors for all RPCs.
    Otherwise, it will return dummy responses.
    """
    self.port = find_free_port()
    self.grpc_server = grpc.aio.server()

    if self.test_for_error:
      mcp_pb2_grpc.add_McpServicer_to_server(
          FakeErrorServicer(), self.grpc_server
      )
    else:
      mcp_pb2_grpc.add_McpServicer_to_server(FakeServicer(), self.grpc_server)

    self.grpc_server.add_insecure_port(f"localhost:{self.port}")
    await self.grpc_server.start()

  async def stop(self):
    await self.grpc_server.stop(1)


class FakeTestClient:
  """A fake test client used to connect to the test server and send RPCs."""

  def __init__(
      self, port: int, options: Sequence[tuple[str, Any]] | None = None
  ):
    self.channel = grpc.aio.insecure_channel(
        f"localhost:{port}", options=options
    )
    self.stub = mcp_pb2_grpc.McpStub(self.channel)
