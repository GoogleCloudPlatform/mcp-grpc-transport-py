"""Utility functions for gRPC."""

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import grpc
from grpc import aio

from mcp.shared import version

MCP_PROTOCOL_VERSION_KEY = "mcp-protocol-version"
MCP_TOOL_NAME_KEY = "mcp-tool-name"
MCP_RESOURCE_URI_KEY = "mcp-resource-uri"
LATEST_PROTOCOL_VERSION = version.LATEST_PROTOCOL_VERSION
SUPPORTED_PROTOCOL_VERSIONS = version.SUPPORTED_PROTOCOL_VERSIONS

F = TypeVar("F", bound=Callable[..., Any])


async def verify_protocol_version_from_metadata(
    context: aio.ServicerContext[Any, Any],
) -> None:
  """Checks version and sends initial metadata, aborting if version is invalid."""
  protocol_version_str = await _get_protocol_version_from_context(
      context, version.SUPPORTED_PROTOCOL_VERSIONS
  )
  # If get_protocol_version_from_context returns, version is valid.
  await context.send_initial_metadata([
      (MCP_PROTOCOL_VERSION_KEY, protocol_version_str),
  ])


async def _get_protocol_version_from_context(
    context: aio.ServicerContext[Any, Any], supported_versions: Sequence[str],
) -> str | None:
  """Extracts and validates the protocol version from gRPC metadata, in the MCP_PROTOCOL_VERSION_KEY.

  If the mcp-protocol-version provided is missing or not supported, the 
  following steps are followed:
    1. initial metadata including the server's LATEST_PROTOCOL_VERSION is sent 
        back to the client.
    2. The server then aborts the RPC with grpc.StatusCode.UNIMPLEMENTED, 
        providing a message indicating the unsupported version and listing the 
        versions it does support.

  Args:
      context: The gRPC context.
      supported_versions: The list of supported protocol versions.

  Returns:
      The protocol version string from the metadata if it exists and is
      supported, or None otherwise, after aborting the RPC.
  """

  metadata = context.invocation_metadata()
  protocol_version_str = get_metadata_value(metadata, MCP_PROTOCOL_VERSION_KEY)

  # Success case: If the protocol version is provided and supported, return it.
  if (
      protocol_version_str is not None
      and protocol_version_str in supported_versions
  ):
    return protocol_version_str

  # Failure case: If the protocol version is not provided or not supported,
  # send the initial metadata with the supported latest version and
  # abort the RPC with an appropriate error message.

  # Fail in case of both None and empty string
  if not protocol_version_str:
    abort_msg = "Protocol version not provided."
  else:
    abort_msg = "Unsupported protocol version."

  supported_versions_str = ", ".join(supported_versions)
  abort_msg += f" Supported versions are: {supported_versions_str}"

  await context.send_initial_metadata(
      [(MCP_PROTOCOL_VERSION_KEY, version.LATEST_PROTOCOL_VERSION)]
  )
  await context.abort(
      grpc.StatusCode.UNIMPLEMENTED,
      abort_msg,
  )


def get_metadata_value(
    metadata: (aio.Metadata | Sequence[tuple[str, str | bytes]]) | None,
    key: str,
) -> str | None:
  """Extracts a value from gRPC metadata by key.

  Args:
      metadata: The gRPC metadata.
      key: The key of the metadata to extract.

  Returns:
      The value of the metadata if found, otherwise None.
  """
  if not metadata:
    return None

  lower_key = key.lower()
  for k, v in metadata:
    if k.lower() == lower_key:
      return v.decode("utf-8") if isinstance(v, bytes) else v

  return None
