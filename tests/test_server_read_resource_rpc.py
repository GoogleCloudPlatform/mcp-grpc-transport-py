import unittest

from absl.testing import absltest
from absl.testing import parameterized
import grpc
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import convert_types

from mcp_grpc_transport_proto import mcp_messages_pb2


class TestReadResourceRPC(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Test suite for ReadResource RPC handler in the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithResources()
    await self.test_server.start_grpc_server()

    self.test_client = test_utils.FakeTestClient(
        self.test_server.port
    )

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  @parameterized.named_parameters(
      dict(
          testcase_name="_TextResource",
          uri="test://data",
          mime_type="text/plain",
          text="resource data",
          blob=b"",
      ),
      dict(
          testcase_name="_BinaryResource",
          uri="test://binary_resource",
          mime_type="application/octet-stream",
          text="",
          blob=b"binary data",
      ),
      dict(
          testcase_name="_EmptyResource",
          uri="test://empty_resource",
          mime_type="text/plain",
          text="",
          blob=b"",
      ),
  )
  async def test_read_resource_success(self, uri, mime_type, text, blob):
    """Tests the ReadResource RPC."""

    request = mcp_messages_pb2.ReadResourceRequest(uri=uri)
    response = await self.test_client.stub.ReadResource(
        request, metadata=self.test_server.version_metadata
    )
    resource_contents, = response.resource
    expected_resource_contents = mcp_messages_pb2.ResourceContents(
        uri=uri,
        mime_type=mime_type,
        text=text,
        blob=blob,
    )
    self.assertEqual(expected_resource_contents, resource_contents)

  async def test_read_resource_template_success(self):
    """Tests the ReadResource RPC."""

    request = mcp_messages_pb2.ReadResourceRequest(uri="test://template/world")
    response = await self.test_client.stub.ReadResource(
        request, metadata=self.test_server.version_metadata
    )
    resource_contents, = response.resource
    expected_resource_contents = mcp_messages_pb2.ResourceContents(
        uri="test://template/world",
        mime_type="text/plain",
        text="Hello, world!",
        blob=b"",
    )
    self.assertEqual(expected_resource_contents, resource_contents)

  async def test_read_unknown_resource(self):
    """Tests ReadResource RPC aborts on ValueError("Unknown resource")."""

    request = mcp_messages_pb2.ReadResourceRequest(uri="test://non-existent")
    with self.assertRaises(grpc.aio.AioRpcError) as context:
      await self.test_client.stub.ReadResource(
          request, metadata=self.test_server.version_metadata
      )

    rpc_error = context.exception
    self.assertEqual(rpc_error.code(), grpc.StatusCode.NOT_FOUND)
    self.assertIn("Error during ReadResource call", rpc_error.details())
    self.assertIn("ValueError('Unknown resource", rpc_error.details())

  async def test_read_resource_on_exception(self):
    """Tests the ReadResource RPC aborts correctly when an exception occurs."""
    # Mock the resource_contents_to_proto function to raise a TypeError
    # This will simulate an exception that results in the RPC getting aborted
    # with an INTERNAL error.

    with unittest.mock.patch.object(
        convert_types,
        "resource_contents_to_proto",
        side_effect=TypeError("Intentional TypeError"),
        autospec=True,
    ):
      request = mcp_messages_pb2.ReadResourceRequest(uri="test://data")
      with self.assertRaises(grpc.aio.AioRpcError) as context:
        await self.test_client.stub.ReadResource(
            request, metadata=self.test_server.version_metadata
        )

      rpc_error = context.exception
      self.assertEqual(rpc_error.code(), grpc.StatusCode.INTERNAL)
      self.assertIn("Error during ReadResource call", rpc_error.details())
      self.assertIn("Intentional TypeError", rpc_error.details())


class TestReadLargeTextResourceRPC(unittest.IsolatedAsyncioTestCase):
  """Test suite for ReadResource RPC response for large text resources."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithResources()
    await self.test_server.start_grpc_server()

    self.test_client = None

  async def asyncTearDown(self):
    if self.test_client:
      await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_read_large_text_resource_success(self):
    """Tests the ReadResource RPC for a large text resource succeeds."""

    self.test_client = test_utils.FakeTestClient(
        self.test_server.port,
        options=[
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
        ],
    )

    request = mcp_messages_pb2.ReadResourceRequest(
        uri="test://large_text_resource"
    )

    response = await self.test_client.stub.ReadResource(
        request, metadata=self.test_server.version_metadata
    )
    resource_contents, = response.resource
    expected_resource_contents = mcp_messages_pb2.ResourceContents(
        uri="test://large_text_resource",
        mime_type="text/plain",
        text="a" * (5 * 1024 * 1024),
        blob=b"",
    )
    self.assertEqual(expected_resource_contents, resource_contents)

  async def test_read_large_text_resource_error(self):
    """Tests the ReadResource RPC for a large text resource fails."""
    self.test_client = test_utils.FakeTestClient(
        self.test_server.port,
        # Explicitly set the max receive length to 4MB, which is the
        # default in OSS gRPC Python.
        options=[
            ("grpc.max_receive_message_length", 4 * 1024 * 1024),
        ],
    )

    request = mcp_messages_pb2.ReadResourceRequest(
        uri="test://large_text_resource",
    )

    with self.assertRaises(grpc.aio.AioRpcError) as context:
      await self.test_client.stub.ReadResource(
          request, metadata=self.test_server.version_metadata
      )

    rpc_error = context.exception
    self.assertEqual(rpc_error.code(), grpc.StatusCode.RESOURCE_EXHAUSTED)
    self.assertIn(
        "CLIENT: Received message larger than max", rpc_error.details()
    )


if __name__ == "__main__":
  absltest.main()
