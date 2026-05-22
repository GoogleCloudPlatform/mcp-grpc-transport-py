import unittest

from absl.testing import absltest
from absl.testing import parameterized
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import convert_types


class TestReadResourceRPC(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Client-side test suite for read_resource implementation."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithResources()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  @parameterized.named_parameters(
      dict(
          testcase_name="_TextResource",
          expected_resource_item=mcp_types.TextResourceContents(
              uri="test://data",
              mimeType="text/plain",
              text="resource data",
          ),
      ),
      dict(
          testcase_name="_BinaryResource",
          expected_resource_item=mcp_types.BlobResourceContents(
              uri="test://binary_resource",
              mimeType="application/octet-stream",
              blob=b"binary data",
          ),
      ),
      dict(
          testcase_name="_EmptyResource",
          expected_resource_item=mcp_types.TextResourceContents(
              uri="test://empty_resource",
              mimeType="text/plain",
              text="",
          ),
      ),
      dict(
          testcase_name="_TextTemplate",
          expected_resource_item=mcp_types.TextResourceContents(
              uri="test://template/world",
              mimeType="text/plain",
              text="Hello, world!",
          ),
      ),
  )
  async def test_read_resource_success(self, *, expected_resource_item):
    """Tests the read_resource client side implementation."""
    response = await self.client_session.read_resource(
        uri=expected_resource_item.uri
    )

    resource_contents = response.contents
    self.assertLen(resource_contents, 1)

    resource, = resource_contents
    self.assertEqual(resource, expected_resource_item)

  async def test_read_unknown_resource(self):
    """Tests read_resource fails with INVALID_REQUEST for an unknown resource.
    """

    with self.assertRaises(mcp_exceptions.McpError) as context:
      await self.client_session.read_resource(uri="test://non-existent")

    error: mcp_types.ErrorData = context.exception.error
    self.assertEqual(error.code, mcp_types.INVALID_REQUEST)
    self.assertIn("Error during ReadResource call", error.message)
    self.assertIn("ValueError('Unknown resource", error.message)

  async def test_read_resource_on_exception(self):
    """Tests the ReadResource RPC aborts correctly when an exception occurs."""

    # Mock the resource_contents_to_proto function to raise TypeError in server.
    # This will simulate an exception that results in the RPC getting aborted
    # with an INTERNAL error.
    with unittest.mock.patch.object(
        convert_types,
        "resource_contents_to_proto",
        side_effect=TypeError("Intentional TypeError"),
        autospec=True,
    ):

      with self.assertRaises(mcp_exceptions.McpError) as context:
        await self.client_session.read_resource(uri="test://data")

      error: mcp_types.ErrorData = context.exception.error
      self.assertEqual(error.code, mcp_types.INTERNAL_ERROR)
      self.assertIn("Error during ReadResource call", error.message)
      self.assertIn("Intentional TypeError", error.message)


class TestReadLargeTextResourceRPC(unittest.IsolatedAsyncioTestCase):
  """Test suite for ReadResource RPC response for large text resources."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithResources()
    await self.test_server.start_grpc_server()

    self.client_session = None

  async def asyncTearDown(self):
    if self.client_session:
      await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_read_large_text_resource_success(self):
    """Tests the ReadResource RPC for a large text resource succeeds."""
    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
        grpc_settings=mcp_grpc_client.GRPCClientTransportSettings(
            options=[("grpc.max_receive_message_length", 10 * 1024 * 1024)],
        ),
    )

    response = await self.client_session.read_resource(
        uri="test://large_text_resource"
    )
    resource_contents, = response.contents
    expected_resource_contents = mcp_types.TextResourceContents(
        uri="test://large_text_resource",
        mimeType="text/plain",
        text="a" * (5 * 1024 * 1024),
    )

    self.assertEqual(resource_contents, expected_resource_contents)

  async def test_read_large_text_resource_error(self):
    """Tests the ReadResource RPC for a large text resource fails."""
    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
        grpc_settings=mcp_grpc_client.GRPCClientTransportSettings(
            # Explicitly set the max receive length to 4MB, which is the
            # default in OSS gRPC Python.
            options=[("grpc.max_receive_message_length", 4 * 1024 * 1024)],
        ),
    )

    with self.assertRaises(mcp_exceptions.McpError) as context:
      await self.client_session.read_resource(
          uri="test://large_text_resource"
      )

    error = context.exception.error
    self.assertEqual(error.code, mcp_types.INTERNAL_ERROR)
    self.assertIn("CLIENT: Received message larger than max", error.message)


if __name__ == "__main__":
  absltest.main()
