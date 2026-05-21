import unittest

from absl.testing import absltest
from absl.testing import parameterized
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from tests import test_utils


class TestReadResourceRPC(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Client-side test suite for read_resource implementation."""

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
          testcase_name="_text_resource",
          expected_resource_item=mcp_types.TextResourceContents(
              uri="test://data",
              mimeType="text/plain",
              text="resource data",
          ),
      ),
      dict(
          testcase_name="_text_template",
          expected_resource_item=mcp_types.TextResourceContents(
              uri="test://template",
              mimeType="text/plain",
              text="Hello World!",
          ),
      ),
  )
  async def test_read_resource_success(self, expected_resource_item):
    """Tests the read_resource client side implementation."""

    response = await self.client_session.read_resource(
        uri=expected_resource_item.uri
    )

    resource_contents = response.contents
    self.assertLen(resource_contents, 1)

    resource, = resource_contents
    self.assertEqual(resource, expected_resource_item)


class TestClientReadResourceRPCFailure(unittest.IsolatedAsyncioTestCase):
  """Client side failure tests for list_resources & list_resource_templates."""

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

  async def test_read_resource_abort_failure(self):
    """Tests client side error handling in case of an abort from the server."""

    with self.assertRaises(mcp_exceptions.McpError) as context:
      await self.client_session.read_resource(uri="test://unused_uri")

    with self.subTest(name="VerifyErrorCode"):
      self.assertEqual(context.exception.error.code, mcp_types.INTERNAL_ERROR)

    with self.subTest(name="VerifyErrorMessage"):
      exception_msg = context.exception.error.message
      self.assertRegex(
          exception_msg, r"AioRpcError.*\n.*status = StatusCode.INTERNAL"
      )


if __name__ == "__main__":
  absltest.main()
