"""Unit tests for error mappings."""

from absl.testing import absltest
import grpc
from mcp.shared.exceptions import MCPError
import mcp.types as mcp_types

from mcp_grpc_transport import errors

from tests.helpers import make_fake_aio_rpc_error


class McpErrorToGrpcStatusTest(absltest.TestCase):

    def test_emits_trailing_metadata_for_known_codes(self):
        err = MCPError(code=mcp_types.PARSE_ERROR, message="parse fail")
        status, msg, metadata = errors.mcp_error_to_grpc_status(err)
        self.assertEqual(status, grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(msg, "parse fail")
        self.assertEqual(metadata, ((errors.MCP_CODE_METADATA_KEY, str(mcp_types.PARSE_ERROR)),))

        err = MCPError(code=mcp_types.METHOD_NOT_FOUND, message="no method")
        status, _, metadata = errors.mcp_error_to_grpc_status(err)
        self.assertEqual(status, grpc.StatusCode.UNIMPLEMENTED)
        self.assertEqual(metadata, ((errors.MCP_CODE_METADATA_KEY, str(mcp_types.METHOD_NOT_FOUND)),))

    def test_unknown_code_falls_back_to_internal_but_preserves_in_metadata(self):
        err = MCPError(code=-12345, message="custom")
        status, _, metadata = errors.mcp_error_to_grpc_status(err)
        self.assertEqual(status, grpc.StatusCode.INTERNAL)
        self.assertEqual(metadata, ((errors.MCP_CODE_METADATA_KEY, "-12345"),))


class GrpcErrorToMcpErrorTest(absltest.TestCase):

    def test_prefers_trailing_metadata_over_status_map(self):
        # Trailing metadata wins over the status-code fallback: even though
        # INVALID_ARGUMENT defaults to INVALID_PARAMS, the metadata override
        # restores the exact original code (PARSE_ERROR).
        rpc_err = make_fake_aio_rpc_error(
            grpc.StatusCode.INVALID_ARGUMENT,
            "Anything",
            mcp_code=mcp_types.PARSE_ERROR,
        )
        mcp_err = errors.grpc_error_to_mcp_error(rpc_err, "Prefix")
        self.assertEqual(mcp_err.code, mcp_types.PARSE_ERROR)
        self.assertIn("Prefix: Anything", mcp_err.message)

    def test_falls_back_to_status_map_without_metadata(self):
        rpc_err = make_fake_aio_rpc_error(grpc.StatusCode.UNIMPLEMENTED, "Not implemented")
        mcp_err = errors.grpc_error_to_mcp_error(rpc_err)
        self.assertEqual(mcp_err.code, mcp_types.METHOD_NOT_FOUND)
        self.assertEqual(mcp_err.message, "Not implemented")

        rpc_err = make_fake_aio_rpc_error(grpc.StatusCode.INTERNAL, "Crash")
        self.assertEqual(errors.grpc_error_to_mcp_error(rpc_err).code, mcp_types.INTERNAL_ERROR)

        rpc_err = make_fake_aio_rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED, "Timeout")
        self.assertEqual(errors.grpc_error_to_mcp_error(rpc_err).code, mcp_types.REQUEST_TIMEOUT)

    def test_ignores_invalid_metadata(self):
        rpc_err = make_fake_aio_rpc_error(grpc.StatusCode.INVALID_ARGUMENT, "bad")
        # Inject malformed metadata directly.
        rpc_err._trailing = ((errors.MCP_CODE_METADATA_KEY, "not-an-int"),)
        mcp_err = errors.grpc_error_to_mcp_error(rpc_err)
        # Falls back to the status-code map (INVALID_ARGUMENT -> INVALID_PARAMS).
        self.assertEqual(mcp_err.code, mcp_types.INVALID_PARAMS)


class ExceptionToMcpErrorTest(absltest.TestCase):

    def test_mcp_error_passes_through_unchanged(self):
        err = MCPError(code=mcp_types.PARSE_ERROR, message="test")
        self.assertIs(errors.exception_to_mcp_error(err), err)

    def test_aio_rpc_error_is_mapped(self):
        rpc_err = make_fake_aio_rpc_error(grpc.StatusCode.UNIMPLEMENTED, "Unimplemented")
        mcp_err = errors.exception_to_mcp_error(rpc_err)
        self.assertEqual(mcp_err.code, mcp_types.METHOD_NOT_FOUND)

    def test_generic_exception_becomes_internal_error(self):
        mcp_err = errors.exception_to_mcp_error(ValueError("bad value"), "Prefix")
        self.assertEqual(mcp_err.code, mcp_types.INTERNAL_ERROR)
        self.assertIn("Prefix: bad value", mcp_err.message)


if __name__ == "__main__":
    absltest.main()
