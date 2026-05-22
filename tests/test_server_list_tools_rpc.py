import unittest

from absl.testing import absltest
from google.protobuf import json_format
import grpc
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import convert_types


class TestListToolsRPC(unittest.IsolatedAsyncioTestCase):
  """Tests the ListTools RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.test_client = test_utils.FakeTestClient(
        self.test_server.port
    )

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_list_tools_success(self):
    """Tests the ListTools RPC."""

    request = mcp_messages_pb2.ListToolsRequest()
    response = await self.test_client.stub.ListTools(
        request, metadata=self.test_server.version_metadata
    )
    tools_in_response = response.tools

    with self.subTest(name="VerifyAllAddedTools"):
      self.assertEqual(len(tools_in_response), self.test_server.num_tools)
      tool_names = [t.name for t in tools_in_response]
      self.assertIn("add", tool_names)
      self.assertIn("echo", tool_names)

    add_tool: mcp_messages_pb2.Tool = next(
        t for t in tools_in_response if t.name == "add"
    )

    with self.subTest(name="VerifyAddToolInputSchema"):
      self.assertEqual(add_tool.description, "Add two numbers.")
      self.assertIn("properties", add_tool.input_schema)
      self.assertIn("a", add_tool.input_schema["properties"])
      self.assertIn("b", add_tool.input_schema["properties"])

    with self.subTest(name="VerifyAddToolOutputSchema"):
      # FastMCP might not set output_schema by default for simple types
      # so we skip strict output_schema checks unless we define Pydantic models
      # Verify outputSchema
      self.assertTrue(
          add_tool.HasField("output_schema"), "output_schema should be present"
      )
      self.assertIn("properties", add_tool.output_schema)
      self.assertIn("result", add_tool.output_schema["properties"])

  async def test_list_tools_parse_error(self):
    """Tests ListTools RPC with json_format.ParseError."""

    # Mock the tool_to_proto function to raise a ParseError
    # This will simulate an invalid schema error
    with unittest.mock.patch.object(
        convert_types,
        "tool_to_proto",
        side_effect=json_format.ParseError("Invalid schema"),
        autospec=True,
    ):
      request = mcp_messages_pb2.ListToolsRequest()
      with self.assertRaises(grpc.RpcError) as context:
        await self.test_client.stub.ListTools(
            request, metadata=self.test_server.version_metadata
        )

      rpc_error = context.exception
      self.assertEqual(rpc_error.code(), grpc.StatusCode.INTERNAL)
      self.assertIn("Error during ListTools call", rpc_error.details())
      self.assertIn("Invalid schema", rpc_error.details())


if __name__ == "__main__":
  absltest.main()
