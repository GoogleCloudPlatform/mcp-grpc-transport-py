import unittest
from unittest import mock

from absl.testing import absltest
import grpc
from mcp_grpc_transport.server import grpc_server
from tests import test_utils
from mcp_grpc_transport.utils import convert_types

from mcp_grpc_transport_proto import mcp_messages_pb2

class TestListResourcesAndTemplatesRPC(unittest.IsolatedAsyncioTestCase):
  """Test suite for ListResources and ListResourceTemplates server handlers."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithResources()
    await self.test_server.start_grpc_server()

    self.test_client = test_utils.FakeTestClient(
        self.test_server.port
    )

  async def asyncTearDown(self):
    await self.test_client.channel.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_list_resources_success(self):
    """Tests the ListResources RPC."""

    request = mcp_messages_pb2.ListResourcesRequest()
    response = await self.test_client.stub.ListResources(
        request, metadata=self.test_server.version_metadata
    )
    resources = response.resources

    with self.subTest(name="VerifyAddedResources"):
      self.assertEqual(len(resources), self.test_server.num_resources)
      resource_names = [r.name for r in resources]
      self.assertIn("test_resource", resource_names)
      self.assertIn("binary_resource", resource_names)

    test_resource = next(t for t in resources if t.name == "test_resource")
    expected_resource = mcp_messages_pb2.Resource(
        name="test_resource",
        uri="test://data",
        description="A test resource.",
        mime_type="text/plain",
        title="",
    )
    with self.subTest(name="VerifyTestResourceAttributes"):
      self.assertEqual(expected_resource, test_resource)

  async def test_list_resources_error(self):
    """Tests the ListResources RPC aborts correctly when an error occurs."""

    # Mock the resource_to_proto function to raise a TypeError
    # This will simulate an exception that results in the RPC getting aborted
    with mock.patch.object(
        convert_types,
        "resource_to_proto",
        side_effect=TypeError("Intentional TypeError"),
        autospec=True,
    ):
      request = mcp_messages_pb2.ListResourcesRequest()
      with self.assertRaises(grpc.aio.AioRpcError) as context:
        await self.test_client.stub.ListResources(
            request, metadata=self.test_server.version_metadata
        )

      rpc_error = context.exception
      self.assertEqual(rpc_error.code(), grpc.StatusCode.INTERNAL)
      self.assertIn("Error during ListResources call", rpc_error.details())
      self.assertIn("Intentional TypeError", rpc_error.details())

  async def test_list_resource_templates_success(self):
    """Tests the ListResourceTemplates RPC."""

    request = mcp_messages_pb2.ListResourceTemplatesRequest()
    response = await self.test_client.stub.ListResourceTemplates(
        request, metadata=self.test_server.version_metadata
    )
    resource_templates = response.resource_templates

    with self.subTest(name="VerifyAddedResourceTemplates"):
      self.assertEqual(
          len(resource_templates), self.test_server.num_resource_templates
      )
      resource_names = [r.name for r in resource_templates]
      self.assertIn("template_resource", resource_names)

    test_template: mcp_messages_pb2.ResourceTemplate = next(
        t for t in resource_templates if t.name == "template_resource"
    )

    expected_template = mcp_messages_pb2.ResourceTemplate(
        name="template_resource",
        uri_template="test://template/{name}",
        description="A template resource.",
        mime_type="text/plain",
    )
    with self.subTest(name="VerifyTestResourceTemplateAttributes"):
      self.assertEqual(expected_template, test_template)

  async def test_list_resource_templates_error(self):
    """Tests ListResourceTemplates RPC aborts correctly when error occurs."""

    # Mock the resource_to_proto function to raise a TypeError
    # This will simulate an exception that results in the RPC getting aborted
    with mock.patch.object(
        convert_types,
        "resource_template_to_proto",
        side_effect=TypeError("Intentional TypeError"),
        autospec=True,
    ):
      request = mcp_messages_pb2.ListResourceTemplatesRequest()
      with self.assertRaises(grpc.aio.AioRpcError) as context:
        await self.test_client.stub.ListResourceTemplates(
            request, metadata=self.test_server.version_metadata
        )

      rpc_error = context.exception
      self.assertEqual(rpc_error.code(), grpc.StatusCode.INTERNAL)
      self.assertIn(
          "Error during ListResourceTemplates call", rpc_error.details()
      )
      self.assertIn("Intentional TypeError", rpc_error.details())


if __name__ == "__main__":
  absltest.main()
