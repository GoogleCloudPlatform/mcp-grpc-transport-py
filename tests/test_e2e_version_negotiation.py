import unittest

from absl.testing import absltest
from absl.testing import parameterized
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils


class TestE2EVersionNegotiationToolRPCs(
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


class TestE2EVersionNegotiationResourceRPCs(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Tests the version negotiation logic of the MCP gRPC client and server.

  This class tests RPCs related to resources, namely ListResources,
  ListResourceTemplates, and ReadResource.
  """

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
          version="2025-06-20",
          testcase_name="_unsupported_version",
      ),
      dict(
          version="",
          testcase_name="_missing_version",
      ),
  )
  async def test_list_resources_version_negotiation_success(self, *, version):
    """Tests version negotiation retry logic for ListResources RPCs."""

    self.client_session.negotiated_version = version

    try:
      response = await self.client_session.list_resources()
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "ListResources RPC unexpectedly failed with UNIMPLEMENTED status"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid and contains some
    # of the expected resources.
    resources_in_response = response.resources

    with self.subTest(name="VerifyNumberOfResources"):
      self.assertLen(resources_in_response, self.test_server.num_resources)

    with self.subTest(name="VerifyResourceNames"):
      resource_names = [t.name for t in resources_in_response]
      self.assertIn("test_resource", resource_names)
      self.assertIn("binary_resource", resource_names)

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
  async def test_list_resource_templates_version_negotiation_success(
      self, *, version
  ):
    """Tests version negotiation retry logic for ListResourceTemplates RPCs."""

    self.client_session.negotiated_version = version

    try:
      response = await self.client_session.list_resource_templates()
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "ListResourceTemplates RPC unexpectedly failed with UNIMPLEMENTED"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid and contains some
    # of the expected resources.
    resource_templates_in_response = response.resourceTemplates

    with self.subTest(name="VerifyNumberOfResourceTemplates"):
      self.assertLen(
          resource_templates_in_response,
          self.test_server.num_resource_templates,
      )

    with self.subTest(name="VerifyResourceNames"):
      resource_names = [t.name for t in resource_templates_in_response]
      self.assertIn("template_resource", resource_names)

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
  async def test_read_resource_version_negotiation_success(self, *, version):
    self.client_session.negotiated_version = version

    try:
      response = await self.client_session.read_resource(uri="test://data")
    except mcp_exceptions.McpError as e:
      if e.error.code == mcp_types.METHOD_NOT_FOUND:
        self.fail(
            "ListResourceTemplates RPC unexpectedly failed with UNIMPLEMENTED"
            f" (equivalent to mcp_types.METHOD_NOT_FOUND) without retrying: {e}"
        )
      raise

    # Verify that the response received after retry is valid.
    self.assertIsInstance(response, mcp_types.ReadResourceResult)

    expected_resource_contents = mcp_types.TextResourceContents(
        uri="test://data",
        mimeType="text/plain",
        text="resource data",
    )

    contents, = response.contents
    self.assertEqual(contents, expected_resource_contents)


if __name__ == "__main__":
  absltest.main()
