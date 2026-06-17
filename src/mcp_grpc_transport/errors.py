"""Error mapping between MCP and gRPC."""

import logging
import grpc
from mcp import types as mcp_types
from mcp.shared.exceptions import MCPError

logger = logging.getLogger(__name__)

# Map JSON-RPC error codes to gRPC Status Codes
MCP_TO_GRPC_CODE_MAP = {
    mcp_types.PARSE_ERROR: grpc.StatusCode.INVALID_ARGUMENT,
    mcp_types.INVALID_REQUEST: grpc.StatusCode.INVALID_ARGUMENT,
    mcp_types.METHOD_NOT_FOUND: grpc.StatusCode.UNIMPLEMENTED,
    mcp_types.INVALID_PARAMS: grpc.StatusCode.INVALID_ARGUMENT,
    mcp_types.INTERNAL_ERROR: grpc.StatusCode.INTERNAL,
}

# Map gRPC Status Codes to JSON-RPC error codes
GRPC_TO_MCP_CODE_MAP = {
    grpc.StatusCode.INVALID_ARGUMENT: mcp_types.INVALID_PARAMS,
    grpc.StatusCode.UNIMPLEMENTED: mcp_types.METHOD_NOT_FOUND,
    grpc.StatusCode.INTERNAL: mcp_types.INTERNAL_ERROR,
    grpc.StatusCode.UNAVAILABLE: mcp_types.INTERNAL_ERROR,
    grpc.StatusCode.NOT_FOUND: mcp_types.INVALID_REQUEST,
    grpc.StatusCode.DEADLINE_EXCEEDED: mcp_types.REQUEST_TIMEOUT,
}

def mcp_error_to_grpc_status(error: MCPError) -> tuple[grpc.StatusCode, str]:
    """Maps an MCPError to a gRPC StatusCode and details string."""
    code = error.error.code
    message = error.error.message
    grpc_code = MCP_TO_GRPC_CODE_MAP.get(code, grpc.StatusCode.INTERNAL)
    return grpc_code, message

def grpc_error_to_mcp_error(
    grpc_error: grpc.aio.AioRpcError,
    error_msg_prefix: str,
) -> MCPError:
    """Converts a gRPC AioRpcError to an MCPError."""
    grpc_code = grpc_error.code()
    details = grpc_error.details() or ""
    
    # Try to determine if details contain a more specific error
    details_lower = details.lower()
    if grpc_code == grpc.StatusCode.INVALID_ARGUMENT:
        if "parse error" in details_lower:
            mcp_code = mcp_types.PARSE_ERROR
        elif "invalid request" in details_lower:
            mcp_code = mcp_types.INVALID_REQUEST
        else:
            mcp_code = mcp_types.INVALID_PARAMS
    else:
        mcp_code = GRPC_TO_MCP_CODE_MAP.get(grpc_code, mcp_types.INTERNAL_ERROR)
        
    return MCPError(
        code=mcp_code,
        message=f"{error_msg_prefix}: {details}" if error_msg_prefix else details,
    )

def exception_to_mcp_error(
    error: Exception,
    error_msg_prefix: str = "",
) -> MCPError:
    """Converts a generic exception (including AioRpcError) to an MCPError."""
    if isinstance(error, MCPError):
        return error
        
    if isinstance(error, grpc.aio.AioRpcError):
        return grpc_error_to_mcp_error(error, error_msg_prefix)
        
    # Generic fallback
    message = str(error)
    return MCPError(
        code=mcp_types.INTERNAL_ERROR,
        message=f"{error_msg_prefix}: {message}" if error_msg_prefix else message,
    )
