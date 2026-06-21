"""Unit tests for error mappings."""

import grpc
from mcp.shared.exceptions import MCPError
import mcp.types as mcp_types
from mcp_grpc_transport import errors


def test_mcp_error_to_grpc_status_emits_trailing_metadata():
    err = MCPError(code=mcp_types.PARSE_ERROR, message="parse fail")
    status, msg, metadata = errors.mcp_error_to_grpc_status(err)
    assert status == grpc.StatusCode.INVALID_ARGUMENT
    assert msg == "parse fail"
    assert metadata == ((errors.MCP_CODE_METADATA_KEY, str(mcp_types.PARSE_ERROR)),)

    err = MCPError(code=mcp_types.METHOD_NOT_FOUND, message="no method")
    status, msg, metadata = errors.mcp_error_to_grpc_status(err)
    assert status == grpc.StatusCode.UNIMPLEMENTED
    assert metadata == ((errors.MCP_CODE_METADATA_KEY, str(mcp_types.METHOD_NOT_FOUND)),)

    # Custom / unknown MCP code falls back to INTERNAL but is still preserved.
    err = MCPError(code=-12345, message="custom")
    status, msg, metadata = errors.mcp_error_to_grpc_status(err)
    assert status == grpc.StatusCode.INTERNAL
    assert metadata == ((errors.MCP_CODE_METADATA_KEY, "-12345"),)


def test_grpc_error_prefers_trailing_metadata(fake_aio_rpc_error):
    # Trailing metadata wins over the status-code fallback: even though
    # INVALID_ARGUMENT defaults to INVALID_PARAMS, the metadata override
    # restores the exact original code (PARSE_ERROR).
    rpc_err = fake_aio_rpc_error(
        grpc.StatusCode.INVALID_ARGUMENT,
        "Anything",
        mcp_code=mcp_types.PARSE_ERROR,
    )
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err, "Prefix")
    assert mcp_err.code == mcp_types.PARSE_ERROR
    assert "Prefix: Anything" in mcp_err.message


def test_grpc_error_falls_back_to_status_map(fake_aio_rpc_error):
    rpc_err = fake_aio_rpc_error(grpc.StatusCode.UNIMPLEMENTED, "Not implemented")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err)
    assert mcp_err.code == mcp_types.METHOD_NOT_FOUND
    assert mcp_err.message == "Not implemented"

    rpc_err = fake_aio_rpc_error(grpc.StatusCode.INTERNAL, "Crash")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err)
    assert mcp_err.code == mcp_types.INTERNAL_ERROR

    rpc_err = fake_aio_rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED, "Timeout")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err)
    assert mcp_err.code == mcp_types.REQUEST_TIMEOUT


def test_grpc_error_ignores_invalid_metadata(fake_aio_rpc_error, caplog):
    rpc_err = fake_aio_rpc_error(grpc.StatusCode.INVALID_ARGUMENT, "bad")
    # Inject malformed metadata directly.
    rpc_err._trailing = ((errors.MCP_CODE_METADATA_KEY, "not-an-int"),)
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err)
    # Falls back to the status-code map.
    assert mcp_err.code == mcp_types.INVALID_PARAMS


def test_exception_to_mcp_error(fake_aio_rpc_error):
    # MCPError passes through unchanged.
    err = MCPError(code=mcp_types.PARSE_ERROR, message="test")
    assert errors.exception_to_mcp_error(err) is err

    # AioRpcError is mapped (with metadata-aware decoding).
    rpc_err = fake_aio_rpc_error(grpc.StatusCode.UNIMPLEMENTED, "Unimplemented")
    mcp_err = errors.exception_to_mcp_error(rpc_err)
    assert mcp_err.code == mcp_types.METHOD_NOT_FOUND

    # Generic exception becomes INTERNAL_ERROR.
    mcp_err = errors.exception_to_mcp_error(ValueError("bad value"), "Prefix")
    assert mcp_err.code == mcp_types.INTERNAL_ERROR
    assert "Prefix: bad value" in mcp_err.message
