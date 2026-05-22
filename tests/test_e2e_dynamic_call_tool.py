from typing import Any
import unittest

from absl.testing import absltest
from mcp import types as mcp_types
import mcp_grpc_transport.client as mcp_grpc_client
from mcp_grpc_transport.server import grpc_server
from tests import test_utils


# Helper functions for this test. As it is specific to this test, it is kept
# here instead of in test_utils.
def _make_args_from_input_schema(input_properties: dict[str, Any]):
  """Returns a dictionary of arguments from the input schema."""
  args = {}
  for input_param, input_param_schema in input_properties.items():
    if input_param_schema["type"] == "integer":
      args[input_param] = 10
    elif input_param_schema["type"] == "string":
      args[input_param] = "test"

  return args


def _get_type_from_string(type_string: str) -> Any:
  """Returns the Python type object to compare against from the type string."""
  if type_string == "integer":
    return int
  elif type_string == "string":
    return str
  elif type_string == "object":
    return object
  elif type_string == "boolean":
    return bool
  elif type_string == "null":
    return type(None)
  else:
    raise ValueError(f"Unsupported type: {type_string}")


def _get_required_type(property_schema: dict[str, Any]):
  """Returns the required type from the property schema.

  The property schema can have a type field or an anyOf field as follows:
  'text': {'type': 'string', 'title': 'Text'}
  'mimeType':{'default': None, 'anyOf': [{'type': 'string'}, {'type': 'null'}]

  'anyOf' may also have another nested 'anyOf' field, so this function handles
  it recursively.

  Args:
    property_schema: The property schema to get the required type from.

  Returns:
    The required type from the property schema.
  """
  if "type" in property_schema:
    return _get_type_from_string(property_schema["type"])

  types = set()
  if "anyOf" in property_schema:
    for any_of_schema in property_schema["anyOf"]:
      types.update(_get_required_type(any_of_schema))

    return types


def _parse_required_fields(output_schema: dict[str, Any]) -> dict[str, Any]:
  """Returns a dictionary of required fields and its types from the output schema."""
  if "required" in output_schema:
    return {}

  required_field_types: dict[str, Any] = {}
  required_fields = output_schema["required"]
  properties = output_schema["properties"]

  for required_field in required_fields:
    required_field_types[required_field] = _get_required_type(
        properties[required_field]
    )

  return required_field_types


class TestE2EDynamicCallTool(unittest.IsolatedAsyncioTestCase):
  """Tests using ListTools to get list of tools from the server and then calling the tools dynamically based on the response."""

  async def asyncSetUp(self):
    self.test_server = test_utils.TestServerWithTools()
    await self.test_server.start_grpc_server()

    self.client_session = mcp_grpc_client.GRPCClientSession(
        target=f"localhost:{self.test_server.port}",
    )

  async def asyncTearDown(self):
    await self.client_session.close()
    await grpc_server.stop_grpc_server(self.test_server.grpc_server, 1)

  async def test_dynamic_call_tool(self):
    """Tests the dynamic call tool functionality by calling tools based on response from ListTools RPC."""

    response = await self.client_session.list_tools()

    self.assertIsInstance(response, mcp_types.ListToolsResult)

    tools_in_response = response.tools
    self.assertEqual(len(tools_in_response), self.test_server.num_tools)

    ignorelist = set([
        "invalidTool",
        "tool_with_wrong_output",
        "tool_with_structured_output",
    ])

    for tool in tools_in_response:

      tool_name = tool.name
      if tool_name in ignorelist:
        continue

      with self.subTest(name=f"VerifyCallTool_{tool_name}_succeeds"):
        print(f"Verifying CallTool for tool: {tool_name}")
        input_properties = tool.inputSchema["properties"]
        args = _make_args_from_input_schema(input_properties)

        # Make the tool call with the arguments derived from the input schema.
        # It will fail automatically fail if the call is not successful.
        # No specific assertions are needed here.
        response = await self.client_session.call_tool(
            tool_name, args
        )

        required_fields = _parse_required_fields(tool.outputSchema)
        for field, required_types in required_fields.items():
          self.assertIn(field, response.content)
          if isinstance(required_types, set):
            self.assertTrue(
                any(
                    isinstance(response.content[field], required_type)
                    for required_type in required_types
                )
            )
          else:
            self.assertIsInstance(response.content[field], required_types)


if __name__ == "__main__":
  absltest.main()
