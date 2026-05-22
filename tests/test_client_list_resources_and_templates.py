import unittest

from absl.testing import absltest
from absl.testing import parameterized
from mcp import types as mcp_types
from mcp.shared import exceptions as mcp_exceptions
import mcp_grpc_transport.client as mcp_grpc_client
from tests import test_utils


class TestClientListResourcesAndTemplatesRPCSuccess(
    unittest.IsolatedAsyncioTestCase
):
  """Client side tests for list_resources and list_resource_templates.

  It makes a call to a FakeTestServer which returns a dummy resource and
  resource template. The test verifies that the response is a
  ListResourcesResult and ListResourceTemplatesResult object respectively and
  the objects contain the expected attributes.
  """

  async def asyncSetUp(self):
    self.test_server = test_utils.FakeTestServer()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await self.test_server.stop()

  async def test_list_resources_success(self):
    response = await self.client_session.list_resources()
    self.assertIsInstance(response, mcp_types.ListResourcesResult)

    resources_result = response.resources
    self.assertEqual(len(resources_result), 1)
    resource, = resources_result

    expected_resource = mcp_types.Resource(
        uri="test://data",
        name="Test Resource",
        title="Test Resource",
        mimeType="text/plain",
    )

    self.assertEqual(resource, expected_resource)

  async def test_list_resource_templates_success(self):
    response = await self.client_session.list_resource_templates()
    self.assertIsInstance(response, mcp_types.ListResourceTemplatesResult)

    templates_result = response.resourceTemplates
    self.assertEqual(len(templates_result), 1)
    template, = templates_result

    expected_template = mcp_types.ResourceTemplate(
        uriTemplate="test://{name}",
        name="Test Resource Template",
        description="Test Resource Template",
        mimeType="text/plain",
    )

    self.assertEqual(template, expected_template)


class TestClientListResourcesAndTemplatesRPCFailure(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):
  """Client side failure tests for list_resources & list_resource_templates.

  It makes a call to a FakeTestServer that aborts the RPC. The test verifies
  that the client raises an error with the correct error code and message.
  """

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

  @parameterized.named_parameters(
      dict(
          testcase_name="_list_resources",
          func_name="list_resources",
      ),
      dict(
          testcase_name="_list_resource_templates",
          func_name="list_resource_templates",
      ),
  )
  async def test_abort_failure(self, func_name):
    with self.assertRaises(mcp_exceptions.McpError) as context:
      func = getattr(self.client_session, func_name)
      await func()

    with self.subTest(name="VerifyErrorCode"):
      self.assertEqual(context.exception.error.code, mcp_types.INTERNAL_ERROR)

    with self.subTest(name="VerifyErrorMessage"):
      exception_msg = context.exception.error.message
      self.assertRegex(
          exception_msg, r"AioRpcError.*\n.*status = StatusCode.INTERNAL"
      )


if __name__ == "__main__":
  absltest.main()
