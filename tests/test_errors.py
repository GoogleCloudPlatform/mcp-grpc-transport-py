"""Unit tests for error mappings."""

import grpc
from mcp.shared.exceptions import MCPError
import mcp.types as mcp_types
from mcp_grpc_transport import errors


def test_mcp_error_to_grpc_status():
    err = MCPError(code=mcp_types.PARSE_ERROR, message="parse fail")
    status, msg = errors.mcp_error_to_grpc_status(err)
    assert status == grpc.StatusCode.INVALID_ARGUMENT
    assert msg == "parse fail"
    
    err = MCPError(code=mcp_types.METHOD_NOT_FOUND, message="no method")
    status, msg = errors.mcp_error_to_grpc_status(err)
    assert status == grpc.StatusCode.UNIMPLEMENTED
    
    # default fallback
    err = MCPError(code=-12345, message="custom")
    status, msg = errors.mcp_error_to_grpc_status(err)
    assert status == grpc.StatusCode.INTERNAL


def test_grpc_error_to_mcp_error():
    # AioRpcError is hard to construct directly because it requires internal state,
    # but we can mock it or use the fact that it is a subclass of grpc.RpcError
    # Actually, we can mock it using a helper class
    class MockAioRpcError(grpc.aio.AioRpcError):
        def __init__(self, code, details=""):
            self._code = code
            self._details = details
            
        def code(self):
            return self._code
            
        def details(self):
            return self._details
            
        def __repr__(self):
            return f"MockAioRpcError(code={self._code}, details='{self._details}')"

    rpc_err = MockAioRpcError(grpc.StatusCode.INVALID_ARGUMENT, "Parse error in arguments")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err, "Prefix")
    assert mcp_err.code == mcp_types.PARSE_ERROR
    assert "Prefix: Parse error in arguments" in mcp_err.message
    
    rpc_err = MockAioRpcError(grpc.StatusCode.UNIMPLEMENTED, "Not implemented")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err, "")
    assert mcp_err.code == mcp_types.METHOD_NOT_FOUND
    assert mcp_err.message == "Not implemented"
    
    rpc_err = MockAioRpcError(grpc.StatusCode.INTERNAL, "Crash")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err, "")
    assert mcp_err.code == mcp_types.INTERNAL_ERROR

    rpc_err = MockAioRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, "Timeout")
    mcp_err = errors.grpc_error_to_mcp_error(rpc_err, "")
    assert mcp_err.code == mcp_types.REQUEST_TIMEOUT



def test_exception_to_mcp_error():
    class MockAioRpcError(grpc.aio.AioRpcError):
        def __init__(self, code, details=""):
            self._code = code
            self._details = details
        def code(self): return self._code
        def details(self): return self._details

    # MCPError passes through
    err = MCPError(code=mcp_types.PARSE_ERROR, message="test")
    assert errors.exception_to_mcp_error(err) is err
    
    # AioRpcError is mapped
    rpc_err = MockAioRpcError(grpc.StatusCode.UNIMPLEMENTED, "Unimplemented")
    mcp_err = errors.exception_to_mcp_error(rpc_err)
    assert mcp_err.code == mcp_types.METHOD_NOT_FOUND
    
    # Generic exception
    gen_err = ValueError("bad value")
    mcp_err = errors.exception_to_mcp_error(gen_err, "Prefix")
    assert mcp_err.code == mcp_types.INTERNAL_ERROR
    assert "Prefix: bad value" in mcp_err.message
