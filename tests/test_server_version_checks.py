import unittest

import grpc

from mcp.shared import version
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import version_utils

from google.protobuf import struct_pb2
from google3.testing.pybase import googletest
from mcp_grpc_transport_proto import mcp_messages_pb2


class TestRPCVersionChecks(unittest.IsolatedAsyncioTestCase):
  """Tests the version checking logic of the MCP gRPC server."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.test_client = test_utils.FakeTestClient(
        self.test_server.port
    )

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_list_tools_unsupported_version(self):
    """Tests the ListTools RPC fails with unsupported version metadata.

    The test verifies the following:
    1. The RPC fails with an UNIMPLEMENTED error.
    2. The response metadata is expected to contain the latest protocol version.
    3. The error details are expected to contain the list of supported versions.
    """

    # As of Jan 2025, supported versions are:
    # ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Use a random date to test the unsupported version.
    unsupported_version_metadata = [
        (version_utils.MCP_PROTOCOL_VERSION_KEY, "2025-06-20"),
    ]

    request = mcp_messages_pb2.ListToolsRequest()

    with self.assertRaises(grpc.RpcError) as context:
      await self.test_client.stub.ListTools(
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

  async def test_call_tool_unsupported_version(self):
    """Tests the CallTool RPC fails with unsupported version metadata.

    The test verifies the following:
    1. The RPC fails with an UNIMPLEMENTED error.
    2. The response metadata is expected to contain the latest protocol version.
    3. The error details are expected to contain the list of supported versions.
    """

    args = struct_pb2.Struct()
    args.update({"message": "World"})

    request = mcp_messages_pb2.CallToolRequest(
        request=mcp_messages_pb2.CallToolRequest.Request(
            name="echo", arguments=args
        )
    )

    # Use a random date to test the unsupported version.
    unsupported_version_metadata = [
        (version_utils.MCP_PROTOCOL_VERSION_KEY, "2025-06-20"),
    ]

    with self.assertRaises(grpc.RpcError) as context:
      await self.test_client.stub.CallTool(
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

  async def test_list_tools_missing_version(self):
    """Tests the ListTools RPC fails with missing version.

    The test verifies the following:
    1. The RPC fails with an UNIMPLEMENTED error.
    2. The response metadata is expected to contain the latest protocol version.
    3. The error details are expected to contain the list of supported versions.
    """
    request = mcp_messages_pb2.ListToolsRequest()
    with self.assertRaises(grpc.RpcError) as context:
      await self.test_client.stub.ListTools(request)

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

  async def test_call_tool_missing_version(self):
    """Tests the CallTool RPC fails with missing version.

    The test verifies the following:
    1. The RPC fails with an UNIMPLEMENTED error.
    2. The response metadata is expected to contain the latest protocol version.
    3. The error details are expected to contain the list of supported versions.
    """

    args = struct_pb2.Struct()
    args.update({"message": "World"})

    request = mcp_messages_pb2.CallToolRequest(
        request=mcp_messages_pb2.CallToolRequest.Request(
            name="echo", arguments=args
        )
    )

    with self.assertRaises(grpc.RpcError) as context:
      await self.test_client.stub.CallTool(request)

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
  googletest.main()
