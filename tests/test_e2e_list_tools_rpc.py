from google.protobuf import json_format
import unittest

from absl.testing import absltest
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import convert_types


class TestE2EListToolsRPC(unittest.IsolatedAsyncioTestCase):
  """Tests the ListTools RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_list_tools_success(self):
    """Tests the ListTools RPC."""

    response = await self.client_session.list_tools()

    self.assertIsInstance(response, mcp_types.ListToolsResult)

    tools_in_response = response.tools

    with self.subTest(name="VerifyAllAddedTools"):
      self.assertEqual(len(tools_in_response), self.test_server.num_tools)
      tool_names = [t.name for t in tools_in_response]
      self.assertIn("add", tool_names)
      self.assertIn("echo", tool_names)

    add_tool: mcp_types.Tool = next(
        t for t in tools_in_response if t.name == "add"
    )

    with self.subTest(name="VerifyAddToolInputSchema"):
      self.assertEqual(add_tool.description, "Add two numbers.")
      self.assertIn("properties", add_tool.inputSchema)
      self.assertIn("a", add_tool.inputSchema["properties"])
      self.assertIn("b", add_tool.inputSchema["properties"])

    with self.subTest(name="VerifyAddToolOutputSchema"):
      # FastMCP might not set outputSchema by default for simple types
      # so we skip strict outputSchema checks unless we define Pydantic models
      # Verify outputSchema
      self.assertIsNotNone(
          add_tool.outputSchema, "outputSchema should be present"
      )
      self.assertIn("properties", add_tool.outputSchema)
      self.assertIn("result", add_tool.outputSchema["properties"])

  async def test_list_tools_abort_failure(self):
    """Tests the ListTools RPC with error."""

    # Mock the tool_to_proto function to raise a ParseError from the server side
    # This will simulate an invalid schema error
    with unittest.mock.patch.object(
        convert_types,
        "tool_to_proto",
        autospec=True,
        side_effect=json_format.ParseError("Invalid schema"),
    ):
      with self.assertRaises(mcp_exceptions.McpError) as context:
        await self.client_session.list_tools()

      exception_msg = context.exception.error.message

      self.assertRegex(
          exception_msg, r"AioRpcError.*\n.*status = StatusCode.INTERNAL",
      )


if __name__ == "__main__":
  absltest.main()
