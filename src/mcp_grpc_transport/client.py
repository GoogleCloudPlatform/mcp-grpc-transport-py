"""Client-side gRPC transport for MCP."""

import anyio
import anyio.abc
from collections.abc import Callable, Mapping
import logging
from typing import Any

import grpc
from mcp.shared.dispatcher import CallOptions, Dispatcher, OnNotify, OnRequest
from mcp.shared.exceptions import MCPError, NoBackChannelError
from mcp.shared.transport_context import TransportContext
import mcp.types as mcp_types

from mcp_grpc_transport import convert
from mcp_grpc_transport import errors
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc

logger = logging.getLogger(__name__)


class GRPCClientDispatcher(Dispatcher[TransportContext]):
    """Client-side gRPC dispatcher for MCP."""

    def __init__(
        self,
        address: str | None = None,
        channel: grpc.aio.Channel | None = None,
        *,
        credentials: grpc.ChannelCredentials | None = None,
        options: list[tuple[str, int | str]] | None = None,
        default_timeout: float | None = None,
    ):
        """Initialize the client dispatcher.

        Provide either `address` (managed mode — the dispatcher constructs and
        owns the channel) or `channel` (external mode — the caller owns the
        channel and is responsible for closing it).

        Args:
            address: Target endpoint (e.g. "localhost:50051"). Required when
                `channel` is not given.
            channel: Pre-constructed `grpc.aio.Channel`. When set, lifecycle
                is the caller's responsibility.
            credentials: Channel credentials for secure connections. Ignored
                when `channel` is provided.
            options: Channel options forwarded to `grpc.aio.{insecure,secure}_channel`.
            default_timeout: Fallback per-call timeout (seconds) used when a
                request does not supply one via `CallOptions`.
        """
        if channel is None and address is None:
            raise ValueError("either `address` or `channel` is required")

        self.address = address
        self.external_channel = channel is not None
        self.default_timeout = default_timeout

        if channel is not None:
            self.channel = channel
        elif credentials is not None:
            self.channel = grpc.aio.secure_channel(address, credentials, options=options)
        else:
            self.channel = grpc.aio.insecure_channel(address, options=options)

        self.stub = mcp_pb2_grpc.McpStub(self.channel)
        self._close_event = anyio.Event()
        self._closed = False

    async def run(
        self,
        on_request: OnRequest,
        on_notify: OnNotify,
        on_notify_intercept: Callable[[str, Mapping[str, Any] | None], bool] | None = None,
        *,
        task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        """Drive the client dispatcher.

        Since this is a client-side unary transport, it has no receive loop.
        It calls `task_status.started()` and blocks until `close()` is called.
        The try/finally ensures the managed channel is released if the runner
        task group is cancelled during teardown.
        """
        task_status.started()
        try:
            await self._close_event.wait()
        finally:
            await self.close()

    async def close(self) -> None:
        """Close the dispatcher (idempotent)."""
        self._close_event.set()
        if not self.external_channel and not self._closed:
            self._closed = True
            logger.info("Closing managed gRPC channel")
            await self.channel.close()

    def _resolve_timeout(self, opts: CallOptions | None) -> float | None:
        if opts is not None:
            t = opts.get("timeout")
            if t is not None:
                return t
        return self.default_timeout

    async def send_raw_request(
        self,
        method: str,
        params: Mapping[str, Any] | None,
        opts: CallOptions | None = None,
    ) -> dict[str, Any]:
        """Send a request to the server and await the result.

        gRPC unary transport does not perform an MCP-level initialize handshake
        (no capability negotiation, no protocol-version exchange). Callers must
        not invoke `session.initialize()` against this transport; doing so will
        raise METHOD_NOT_FOUND.

        Dict-in / dict-out: the SDK has already validated `params` against the
        request's Pydantic schema before calling us, and will validate the
        returned dict against the result schema after we return. We translate
        directly between dict and proto without an intermediate Pydantic
        round-trip on either side.
        """
        timeout = self._resolve_timeout(opts)
        # Defensive default so converters can read with .get(); the SDK passes
        # None for methods that take no params.
        params_dict: dict[str, Any] = dict(params) if params else {}

        if method == "tools/list":
            request_proto = mcp_messages_pb2.ListToolsRequest()
            convert.set_common_meta(request_proto, params_dict)
            try:
                response_proto = await self.stub.ListTools(request_proto, timeout=timeout)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, "Error during ListTools")
            return convert.list_tools_result_proto_to_dict(response_proto)

        if method == "tools/call":
            request_proto = convert.call_tool_params_dict_to_proto(params_dict)
            try:
                response_proto = await self.stub.CallTool(request_proto, timeout=timeout)
            except grpc.aio.AioRpcError as e:
                tool_name = params_dict.get("name", "<unknown>")
                raise errors.grpc_error_to_mcp_error(e, f"Error during CallTool for tool {tool_name}")
            return convert.call_tool_result_proto_to_dict(response_proto)

        if method == "resources/list":
            request_proto = mcp_messages_pb2.ListResourcesRequest()
            convert.set_common_meta(request_proto, params_dict)
            try:
                response_proto = await self.stub.ListResources(request_proto, timeout=timeout)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, "Error during ListResources")
            return convert.list_resources_result_proto_to_dict(response_proto)

        if method == "resources/templates/list":
            request_proto = mcp_messages_pb2.ListResourceTemplatesRequest()
            convert.set_common_meta(request_proto, params_dict)
            try:
                response_proto = await self.stub.ListResourceTemplates(request_proto, timeout=timeout)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, "Error during ListResourceTemplates")
            return convert.list_resource_templates_result_proto_to_dict(response_proto)

        if method == "resources/read":
            request_proto = convert.read_resource_params_dict_to_proto(params_dict)
            try:
                response_proto = await self.stub.ReadResource(request_proto, timeout=timeout)
            except grpc.aio.AioRpcError as e:
                uri = params_dict.get("uri", "<unknown>")
                raise errors.grpc_error_to_mcp_error(e, f"Error during ReadResource for {uri}")
            return convert.read_resource_result_proto_to_dict(response_proto)

        raise MCPError(
            code=mcp_types.METHOD_NOT_FOUND,
            message=f"Method not found: {method}",
        )

    async def notify(self, method: str, params: Mapping[str, Any] | None) -> None:
        """Send a notification.

        Unary gRPC has no backchannel; notifications are not supported.
        """
        raise NoBackChannelError(method)
