import unittest
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import convert_types


class TestE2EListResourcesAndTemplatesRPCs(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Tests the e2e flow of ListResources and ListResourceTemplates RPCs."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithResources()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_list_resources_success(self):
    """Tests the e2e flow for list_resources."""

    response = await self.client_session.list_resources()
    self.assertIsInstance(response, mcp_types.ListResourcesResult)

    resources = response.resources

    with self.subTest(name="VerifyAddedResources"):
      self.assertLen(resources, self.test_server.num_resources)
      resource_names = [r.name for r in resources]
      self.assertIn("test_resource", resource_names)
      self.assertIn("binary_resource", resource_names)

    with self.subTest(name="VerifyTestResourceAttributes"):
      test_resource = next(t for t in resources if t.name == "test_resource")
      expected_resource = mcp_types.Resource(
          name="test_resource",
          uri="test://data",
          description="A test resource.",
          mimeType="text/plain",
      )
      self.assertEqual(expected_resource, test_resource)

  async def test_list_resource_templates_success(self):
    """Tests the e2e flow for list_resource_templates."""
    response = await self.client_session.list_resource_templates()
    self.assertIsInstance(response, mcp_types.ListResourceTemplatesResult)

    resource_templates = response.resourceTemplates

    with self.subTest(name="VerifyAddedResourceTemplates"):
      self.assertLen(
          resource_templates, self.test_server.num_resource_templates
      )

    with self.subTest(name="VerifyResourceTemplateResult"):
      resource_names = [r.name for r in resource_templates]
      self.assertIn("template_resource", resource_names)

      test_template: mcp_types.ResourceTemplate = next(
          t for t in resource_templates if t.name == "template_resource"
      )

      expected_template = mcp_types.ResourceTemplate(
          uriTemplate="test://template/{name}",
          name="template_resource",
          description="A template resource.",
          mimeType="text/plain",
      )
      self.assertEqual(expected_template, test_template)

  @parameterized.named_parameters(
      dict(
          testcase_name="_list_resources",
          func_name="list_resources",
          mock_func="resource_to_proto",
      ),
      dict(
          testcase_name="_list_resource_templates",
          func_name="list_resource_templates",
          mock_func="resource_template_to_proto",
      ),
  )
  async def test_error(self, func_name, mock_func):
    """Tests the ListResources RPC aborts correctly when an error occurs."""

    # Mock the convert *_to_proto functions to raise a TypeError
    # This will simulate an exception that results in the RPC getting aborted
    with mock.patch.object(
        convert_types,
        mock_func,
        side_effect=TypeError("Intentional TypeError"),
        autospec=True,
    ):
      with self.assertRaises(mcp_exceptions.McpError) as context:
        func = getattr(self.client_session, func_name)
        await func()

      exception_msg = context.exception.error.message

      self.assertRegex(
          exception_msg, r"AioRpcError.*\n.*status = StatusCode.INTERNAL",
      )


if __name__ == "__main__":
  absltest.main()
