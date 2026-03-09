import unittest


from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils

from google3.testing.pybase import googletest
from google3.testing.pybase import parameterized


class TestE2EVersionNegotiation(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
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

  @parameterized.named_parameters(
      dict(
          version="2025-06-20",
          testcase_name="_unsupported_version",
      ),
      dict(
          version="",
          testcase_name="_missing_version",
      ),
  )
  async def test_list_tools_version_negotiation(self, version):
    """Tests ListTools RPC succeeds on retry with incorrect version metadata."""

    # As of Jan 2026, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Inject a random date to test the unsupported version.
    # or, inject an empty string to test the missing version.
    self.client_session.negotiated_version = version

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

    with self.subTest(name="VerifyNumberOfTools"):
      self.assertLen(tools_in_response, self.test_server.num_tools)

    with self.subTest(name="VerifyToolNames"):
      tool_names = [t.name for t in tools_in_response]
      self.assertIn("add", tool_names)
      self.assertIn("echo", tool_names)

  @parameterized.named_parameters(
      dict(
          version="2025-06-20",
          testcase_name="_unsupported_version",
      ),
      dict(
          version="",
          testcase_name="_missing_version",
      ),
  )
  async def test_call_tool_version_negotiation(self, version):
    """Tests CallTool RPC succeeds on retry with incorrect version metadata."""

    args = {"message": "World"}

    self.client_session.negotiated_version = version

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

    self.assertLen(response.content, 1)
    content, = response.content
    self.assertIsInstance(content, mcp_types.TextContent)

    self.assertEqual(content.text, "Hello World")


if __name__ == "__main__":
  googletest.main()
