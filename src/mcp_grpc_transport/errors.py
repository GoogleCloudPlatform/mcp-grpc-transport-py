"""Error mapping between MCP and gRPC.

The forward map (MCP code -> gRPC StatusCode) is many-to-one (PARSE_ERROR,
INVALID_REQUEST and INVALID_PARAMS all map to INVALID_ARGUMENT). To preserve
fidelity on the return trip we attach the original MCP code in trailing
metadata under MCP_CODE_METADATA_KEY and read it back on the client.
"""

import logging
import grpc
from mcp import types as mcp_types
from mcp.shared.exceptions import MCPError

logger = logging.getLogger(__name__)

MCP_CODE_METADATA_KEY = "mcp-error-code"

MCP_TO_GRPC_CODE_MAP: dict[int, grpc.StatusCode] = {
    mcp_types.PARSE_ERROR: grpc.StatusCode.INVALID_ARGUMENT,
    mcp_types.INVALID_REQUEST: grpc.StatusCode.INVALID_ARGUMENT,
    mcp_types.METHOD_NOT_FOUND: grpc.StatusCode.UNIMPLEMENTED,
    mcp_types.INVALID_PARAMS: grpc.StatusCode.INVALID_ARGUMENT,
    mcp_types.INTERNAL_ERROR: grpc.StatusCode.INTERNAL,
}

GRPC_TO_MCP_CODE_MAP: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.INVALID_ARGUMENT: mcp_types.INVALID_PARAMS,
    grpc.StatusCode.UNIMPLEMENTED: mcp_types.METHOD_NOT_FOUND,
    grpc.StatusCode.INTERNAL: mcp_types.INTERNAL_ERROR,
    grpc.StatusCode.UNAVAILABLE: mcp_types.INTERNAL_ERROR,
    grpc.StatusCode.NOT_FOUND: mcp_types.INVALID_REQUEST,
    grpc.StatusCode.DEADLINE_EXCEEDED: mcp_types.REQUEST_TIMEOUT,
}


def mcp_error_to_grpc_status(
    error: MCPError,
) -> tuple[grpc.StatusCode, str, tuple[tuple[str, str], ...]]:
    """Maps an MCPError to (gRPC StatusCode, details, trailing_metadata).

    The original MCP code is encoded in trailing metadata so the client can
    recover it exactly, even though several MCP codes share one gRPC status.
    """
    code = error.error.code
    message = error.error.message
    grpc_code = MCP_TO_GRPC_CODE_MAP.get(code, grpc.StatusCode.INTERNAL)
    metadata = ((MCP_CODE_METADATA_KEY, str(code)),)
    return grpc_code, message, metadata


def _mcp_code_from_metadata(grpc_error: grpc.aio.AioRpcError) -> int | None:
    """Extract the original MCP code from trailing metadata, if present."""
    metadata = grpc_error.trailing_metadata()
    if not metadata:
        return None
    for entry in metadata:
        # gRPC metadata entries can be (key, value) tuples or Metadatum objects.
        key = entry[0] if isinstance(entry, tuple) else getattr(entry, "key", None)
        value = entry[1] if isinstance(entry, tuple) else getattr(entry, "value", None)
        if key == MCP_CODE_METADATA_KEY and value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                logger.warning("Invalid %s metadata value: %r", MCP_CODE_METADATA_KEY, value)
                return None
    return None


def grpc_error_to_mcp_error(
    grpc_error: grpc.aio.AioRpcError,
    error_msg_prefix: str = "",
) -> MCPError:
    """Converts a gRPC AioRpcError to an MCPError.

    Prefers the MCP code carried in trailing metadata; falls back to the
    static GRPC_TO_MCP_CODE_MAP when no metadata is present (e.g. for errors
    raised by gRPC itself).
    """
    details = grpc_error.details() or ""
    mcp_code = _mcp_code_from_metadata(grpc_error)
    if mcp_code is None:
        mcp_code = GRPC_TO_MCP_CODE_MAP.get(grpc_error.code(), mcp_types.INTERNAL_ERROR)

    message = f"{error_msg_prefix}: {details}" if error_msg_prefix else details
    return MCPError(code=mcp_code, message=message)


def exception_to_mcp_error(
    error: Exception,
    error_msg_prefix: str = "",
) -> MCPError:
    """Converts a generic exception (including AioRpcError) to an MCPError."""
    if isinstance(error, MCPError):
        return error

    if isinstance(error, grpc.aio.AioRpcError):
        return grpc_error_to_mcp_error(error, error_msg_prefix)

    message = str(error)
    return MCPError(
        code=mcp_types.INTERNAL_ERROR,
        message=f"{error_msg_prefix}: {message}" if error_msg_prefix else message,
    )
