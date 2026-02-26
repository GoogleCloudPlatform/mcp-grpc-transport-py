import unittest

from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from tests import test_utils

from google3.testing.pybase import googletest


class TestClientCallToolRPC(unittest.IsolatedAsyncioTestCase):
  """Tests the CallTool RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.FakeTestServer()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await self.test_server.stop()

  async def test_call_tool_success(self):
    response = await self.client_session.call_tool(
        "test_tool", {"test": "test"}
    )

    self.assertIsInstance(response, mcp_types.CallToolResult)
    self.assertFalse(response.isError)

    # Verify that the response received is valid.
    with self.subTest(name="VerifyResponseContents"):
      self.assertEqual(len(response.content), 0)
      self.assertDictEqual(response.structuredContent, {"test": "test"})



class TestClientCallToolRPCFailure(unittest.IsolatedAsyncioTestCase):
  """Tests the CallTool RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.FakeTestServer(test_for_error=True)
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await self.test_server.stop()

  async def test_call_tool_abort_failure(self):
    """Tests the CallTool RPC with error."""

    with self.assertRaises(mcp_exceptions.McpError) as context:
      await self.client_session.call_tool("test_tool", {"test": "test"})

    with self.subTest(name="VerifyErrorCode"):
      self.assertEqual(context.exception.error.code, mcp_types.INTERNAL_ERROR)

    with self.subTest(name="VerifyErrorMessage"):
      exception_msg = context.exception.error.message
      self.assertRegex(
          exception_msg, r"AioRpcError.*\n.*status = StatusCode.INTERNAL"
      )

  async def test_call_tool_error_response(self):
    """Tests the CallTool RPC with error."""

    with self.assertRaises(mcp_exceptions.McpError) as context:
      await self.client_session.call_tool("test_tool", {"send_error": "true"})

    exception_msg = context.exception.error.message

    self.assertEqual(
        "Error response from tool call: Fake error response from CallTool",
        exception_msg,
    )

if __name__ == "__main__":
  googletest.main()
