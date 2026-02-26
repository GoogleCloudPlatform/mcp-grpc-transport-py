import unittest

from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from tests import test_utils

from google3.testing.pybase import googletest


class TestClientVersionNegotiation(unittest.IsolatedAsyncioTestCase):
  """Tests the version negotiation logic of the MCP gRPC client."""

  async def asyncSetUp(self):
    self.test_server = test_utils.FakeTestServer()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await self.test_server.stop()

  async def test_list_tools_version_negotiation_success(self):
    """Tests the version negotiation retry logic for the ListTools RPC."""

    # As of Jan 2026, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Inject a random date to test the unsupported version.
    self.client_session.negotiated_version = "2025-06-20"

    try:
      response = await self.client_session.list_tools()
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "ListTools RPC unexpectedly failed with UNIMPLEMENTED status"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid.
    self.assertIsInstance(response, mcp_types.ListToolsResult)

    tools_in_response = response.tools
    self.assertEqual(len(tools_in_response), 1)

    tool = tools_in_response[0]

    with self.subTest(name="VerifyToolProperties"):
      self.assertEqual(tool.name, "test_tool")
      self.assertEqual(tool.title, "Test Tool")
      self.assertEqual(tool.description, "Test Tool")
      self.assertDictEqual(
          tool.inputSchema,
          {"type": "object", "properties": {"test": {"type": "string"}}},
      )

  async def test_call_tool_version_negotiation_success(self):
    """Tests the version negotiation logic for the CallTool RPC."""

    # As of Jan 2026, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Inject a random date to test the unsupported version.
    self.client_session.negotiated_version = "2025-06-20"

    try:
      response = await self.client_session.call_tool("unused_tool_name")
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            f"CallTool RPC failed with UNIMPLEMENTED without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid.
    self.assertIsInstance(response, mcp_types.CallToolResult)

    self.assertDictEqual(response.structuredContent, {"test": "test"})
    self.assertFalse(response.isError)

if __name__ == "__main__":
  googletest.main()
