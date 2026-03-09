import unittest

from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from tests import test_utils

from google3.testing.pybase import googletest
from google3.testing.pybase import parameterized


class TestClientVersionNegotiation(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
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

  @parameterized.named_parameters(
      dict(
          version="2025-06-20",
          testcase_name="_ListToolsUnsupportedVersion",
          func_name="list_tools",
          params={},
          expected_response=mcp_types.ListToolsResult(
              tools=[
                  mcp_types.Tool(
                      name="test_tool",
                      title="Test Tool",
                      description="Test Tool",
                      inputSchema={
                          "type": "object",
                          "properties": {"test": {"type": "string"}},
                      },
                  )
              ]
          ),
      ),
      dict(
          version="2025-06-20",
          testcase_name="_CallToolUnsupportedVersion",
          func_name="call_tool",
          params={"name": "unused_tool_name"},
          expected_response=mcp_types.CallToolResult(
              content=[],
              structuredContent={"test": "test"},
              isError=False,
          ),
      ),
      dict(
          version="",
          testcase_name="_ListToolsMissingVersion",
          func_name="list_tools",
          params={},
          expected_response=mcp_types.ListToolsResult(
              tools=[
                  mcp_types.Tool(
                      name="test_tool",
                      title="Test Tool",
                      description="Test Tool",
                      inputSchema={
                          "type": "object",
                          "properties": {"test": {"type": "string"}},
                      },
                  )
              ]
          ),
      ),
      dict(
          version="",
          testcase_name="_CallToolMissingVersion",
          func_name="call_tool",
          params={"name": "unused_tool_name"},
          expected_response=mcp_types.CallToolResult(
              content=[],
              structuredContent={"test": "test"},
              isError=False,
          ),
      ),
  )
  async def test_version_negotiation_success(
      self, *, version, func_name, params, expected_response
  ):
    """Tests the version negotiation retry logic for the different RPCs."""

    # As of Jan 2026, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Inject a random date to test the unsupported version.
    # or, inject an empty string to test the missing version.
    self.client_session.negotiated_version = version

    try:
      func = getattr(self.client_session, func_name)
      response = await func(**params)
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "RPC unexpectedly failed with UNIMPLEMENTED status"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid.
    self.assertEqual(response, expected_response)

if __name__ == "__main__":
  googletest.main()
