import unittest

from absl.testing import absltest
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from tests import test_utils


class TestClientListToolsRPCSuccess(unittest.IsolatedAsyncioTestCase):
  """Tests the ListTools RPCs of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.FakeTestServer()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await self.test_server.stop()

  async def test_list_tools_success(self):
    """Tests the ListTools RPC."""

    response = await self.client_session.list_tools()

    self.assertIsInstance(response, mcp_types.ListToolsResult)

    tools_in_response = response.tools
    self.assertEqual(len(tools_in_response), 1)

    tool, = tools_in_response

    with self.subTest(name="VerifyToolFields"):
      self.assertEqual(tool.name, "test_tool")
      self.assertEqual(tool.title, "Test Tool")
      self.assertEqual(tool.description, "Test Tool")
      self.assertDictEqual(
          tool.inputSchema,
          {"type": "object", "properties": {"test": {"type": "string"}}},
      )


class TestClientListToolsRPCFailure(unittest.IsolatedAsyncioTestCase):
  """Tests the ListTools RPCs of the MCP gRPC server for failure cases such as RPC abort from the server."""

  async def asyncSetUp(self):

    # Use a FakeTestServer that will abort the ListTools RPC when called.
    self.test_server = test_utils.FakeTestServer(test_for_error=True)
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await self.test_server.stop()

  async def test_list_tools_abort_failure(self):
    """Tests the ListTools RPC handling in case of an abort from the server."""

    with self.assertRaises(mcp_exceptions.McpError) as context:
      await self.client_session.list_tools()

    with self.subTest(name="VerifyErrorCode"):
      self.assertEqual(context.exception.error.code, mcp_types.INTERNAL_ERROR)

    with self.subTest(name="VerifyErrorMessage"):
      exception_msg = context.exception.error.message
      self.assertRegex(
          exception_msg, r"AioRpcError.*\n.*status = StatusCode.INTERNAL"
      )


if __name__ == "__main__":
  absltest.main()
