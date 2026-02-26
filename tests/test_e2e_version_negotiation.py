import unittest


from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils

from google3.testing.pybase import googletest


class TestE2EVersionNegotiation(unittest.IsolatedAsyncioTestCase):
  """Tests the version negotiation logic of the MCP gRPC client and server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_list_tools_unsupported_version_negotiation(self):
    """Tests the ListTools RPC succeeds with retry on providing unsupported version metadata."""

    # As of Jan 2026, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Use a random date to test the unsupported version.
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

    # Verify that the response received after retry is valid and contains some
    # of the expected tools.
    tools_in_response = response.tools

    with self.subTest(name="VerifyAllAddedTools"):
      self.assertEqual(len(tools_in_response), self.test_server.num_tools)
      tool_names = [t.name for t in tools_in_response]
      self.assertIn("add", tool_names)
      self.assertIn("echo", tool_names)

  async def test_list_tools_missing_version(self):
    """Tests the ListTools RPC succeeds with retry on providing empty version metadata."""

    # Set the negotiated version to an empty string to test the missing version.
    self.client_session.negotiated_version = ""

    try:
      response = await self.client_session.list_tools()
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "ListTools RPC unexpectedly failed with UNIMPLEMENTED status"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid and contains some
    # of the expected tools.
    tools_in_response = response.tools

    with self.subTest(name="VerifyAllAddedTools"):
      self.assertEqual(len(tools_in_response), self.test_server.num_tools)
      tool_names = [t.name for t in tools_in_response]
      self.assertIn("add", tool_names)
      self.assertIn("echo", tool_names)

  async def test_call_tool_unsupported_version(self):
    """Tests the CallTool RPC succeeds with retry on providing unsupported version metadata."""

    args = {"message": "World"}

    # Use a random date to test the unsupported version.
    self.client_session.negotiated_version = "2025-06-20"

    try:
      response = await self.client_session.call_tool(
          name="echo", arguments=args
      )
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "CallTool RPC unexpectedly failed with UNIMPLEMENTED status"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid.
    self.assertIsInstance(response, mcp_types.CallToolResult)

    self.assertEqual(len(response.content), 1)
    content = response.content[0]
    self.assertIsInstance(content, mcp_types.TextContent)

    self.assertEqual(content.text, "Hello World")

  async def test_call_tool_missing_version(self):
    """Tests the CallTool RPC succeeds with retry on providing empty version metadata."""

    args = {"message": "World"}

    # Set the negotiated version to an empty string to test the missing version.
    self.client_session.negotiated_version = ""

    try:
      response = await self.client_session.call_tool(
          name="echo", arguments=args
      )
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "CallTool RPC unexpectedly failed with UNIMPLEMENTED status"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid.
    self.assertIsInstance(response, mcp_types.CallToolResult)

    self.assertEqual(len(response.content), 1)
    content = response.content[0]
    self.assertIsInstance(content, mcp_types.TextContent)

    self.assertEqual(content.text, "Hello World")


if __name__ == "__main__":
  googletest.main()
