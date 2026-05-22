import unittest

from absl.testing import absltest
from absl.testing import parameterized
import grpc
from mcp.shared import version
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import version_utils


class TestRPCVersionChecks(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Tests the version checking logic of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.test_client = test_utils.FakeTestClient(self.test_server.port)

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  @parameterized.named_parameters(
      dict(
          testcase_name="_ListTools",
          rpc_name="ListTools",
          request=mcp_messages_pb2.ListToolsRequest(),
      ),
      dict(
          testcase_name="_CallTool",
          rpc_name="CallTool",
          request=mcp_messages_pb2.CallToolRequest(),
      ),
      dict(
          testcase_name="_ListResources",
          rpc_name="ListResources",
          request=mcp_messages_pb2.ListResourcesRequest(),
      ),
      dict(
          testcase_name="_ListResourceTemplates",
          rpc_name="ListResourceTemplates",
          request=mcp_messages_pb2.ListResourceTemplatesRequest(),
      ),
      dict(
          testcase_name="_ReadResource",
          rpc_name="ReadResource",
          request=mcp_messages_pb2.ReadResourceRequest(),
      ),
  )
  async def test_rpcs_unsupported_version(self, rpc_name, request):
    """Tests the different RPCs fail with unsupported version metadata.

    The test verifies the following:
    1. The RPC fails with an UNIMPLEMENTED error.
    2. The response metadata is expected to contain the latest protocol version.
    3. The error details are expected to contain the list of supported versions.

    Args:
        rpc_name: (str) The name of the RPC to test.
        request: The corresponding Request proto to send to the RPC.
    """

    # As of Jan 2025, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Use a random date to test the unsupported version.
    unsupported_version_metadata = [
        (version_utils.MCP_PROTOCOL_VERSION_KEY, "2025-06-20"),
    ]

    rpc = getattr(self.test_client.stub, rpc_name)

    with self.assertRaises(grpc.RpcError) as context:
      await rpc(
          request, metadata=unsupported_version_metadata
      )

    rpc_error = context.exception
    self.assertEqual(rpc_error.code(), grpc.StatusCode.UNIMPLEMENTED)

    metadata = rpc_error.initial_metadata()
    self.assertEqual(
        metadata[version_utils.MCP_PROTOCOL_VERSION_KEY],
        version.LATEST_PROTOCOL_VERSION,
    )

    supported_versions_str = ", ".join(version.SUPPORTED_PROTOCOL_VERSIONS)
    self.assertIn(
        supported_versions_str,
        rpc_error.details(),
    )

  @parameterized.named_parameters(
      dict(
          testcase_name="_ListTools",
          rpc_name="ListTools",
          request=mcp_messages_pb2.ListToolsRequest(),
      ),
      dict(
          testcase_name="_CallTool",
          rpc_name="CallTool",
          request=mcp_messages_pb2.CallToolRequest(),
      ),
      dict(
          testcase_name="_ListResources",
          rpc_name="ListResources",
          request=mcp_messages_pb2.ListResourcesRequest(),
      ),
      dict(
          testcase_name="_ListResourceTemplates",
          rpc_name="ListResourceTemplates",
          request=mcp_messages_pb2.ListResourceTemplatesRequest(),
      ),
      dict(
          testcase_name="_ReadResource",
          rpc_name="ReadResource",
          request=mcp_messages_pb2.ReadResourceRequest(),
      ),
  )
  async def test_rpcs_missing_version(self, rpc_name, request):
    """Tests the different RPCs fail with missing version.

    The test verifies the following:
    1. The RPC fails with an UNIMPLEMENTED error.
    2. The response metadata is expected to contain the latest protocol version.
    3. The error details are expected to contain the list of supported versions.

    Args:
        rpc_name: (str) The name of the RPC to test.
        request: The corresponding Request proto to send to the RPC.
    """

    rpc = getattr(self.test_client.stub, rpc_name)

    with self.assertRaises(grpc.RpcError) as context:
      await rpc(request)

    rpc_error = context.exception
    self.assertEqual(rpc_error.code(), grpc.StatusCode.UNIMPLEMENTED)

    metadata = rpc_error.initial_metadata()
    self.assertEqual(
        metadata[version_utils.MCP_PROTOCOL_VERSION_KEY],
        version.LATEST_PROTOCOL_VERSION,
    )

    supported_versions_str = ", ".join(version.SUPPORTED_PROTOCOL_VERSIONS)
    self.assertIn(
        supported_versions_str,
        rpc_error.details(),
    )


if __name__ == "__main__":
  absltest.main()
