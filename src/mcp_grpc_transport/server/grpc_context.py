"""A gRPC specific RequestContext that can be used to override MCP's request context."""

from typing import Any, Generic, TYPE_CHECKING
import uuid

from google.protobuf.json_format import MessageToDict
from mcp.shared.context import RequestContext, SessionT
import mcp.types as mcp_types

if TYPE_CHECKING:
  from mcp_grpc_transport_proto import mcp_messages_pb2


class GRPCRequestContext(RequestContext[SessionT, Any, Any], Generic[SessionT]):
  """A gRPC specific RequestContext that can be used to override MCP's request context."""

  @classmethod
  def from_grpc(
      cls,
      request: Any,  # gRPC request object
      session: SessionT,
  ) -> "GRPCRequestContext[SessionT]":
    """Create a RequestContext from a gRPC request."""

    # Extract common fields if present
    common: mcp_messages_pb2.RequestFields | None = getattr(
        request, "common", None
    )
    meta_dict: dict[str, Any] = {}

    if common is not None:
      # Map arbitrary metadata
      if common.HasField("metadata"):
        meta_dict.update(MessageToDict(common.metadata))

    # Create RequestParams.Meta
    meta = mcp_types.RequestParams.Meta(**meta_dict)

    # We don't have a task_id or lifespan context yet as in the official MCP
    # request context. So we use dummy values for now.
    return cls(
        request_id=f"grpc-request-{uuid.uuid4()}",
        # gRPC doesn't inherently have a request ID per call unless we add one
        meta=meta,
        session=session,
        lifespan_context={},
    )
