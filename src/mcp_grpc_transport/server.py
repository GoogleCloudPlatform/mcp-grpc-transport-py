"""Server-side gRPC transport for MCP."""

from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
import logging
from typing import Any

import anyio
import anyio.abc
from google.protobuf.message import Message
import grpc
from mcp.server import MCPServer, Server
from mcp.server.runner import ServerRunner
from mcp.shared.dispatcher import CallOptions, DispatchContext, Dispatcher, OnNotify, OnRequest
from mcp.shared.exceptions import MCPError, NoBackChannelError
from mcp.shared.transport_context import TransportContext
from mcp.types import RequestId

from mcp_grpc_transport import convert
from mcp_grpc_transport import errors
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc

logger = logging.getLogger(__name__)

# Default grace period for managed gRPC server shutdown. None would mean
# immediate termination, which kills in-flight RPCs; 5s gives them a chance
# to finish cleanly while still being a sensible upper bound for tests.
DEFAULT_STOP_GRACE_SECONDS: float = 5.0


class GRPCDispatchContext(DispatchContext[TransportContext]):
    """Per-request context for gRPC transport."""

    def __init__(self, transport_ctx: TransportContext):
        self._transport = transport_ctx
        self._cancel_event = anyio.Event()

    @property
    def transport(self) -> TransportContext:
        return self._transport

    @property
    def can_send_request(self) -> bool:
        # gRPC unary transport is stateless and does not support server-initiated requests.
        return False

    @property
    def request_id(self) -> RequestId | None:
        return None

    @property
    def message_metadata(self) -> None:
        return None

    @property
    def cancel_requested(self) -> anyio.Event:
        return self._cancel_event

    async def progress(self, progress: float, total: float | None = None, message: str | None = None) -> None:
        # Progress notifications require a server->client channel which unary gRPC does not provide.
        # We drop them rather than raise, so handlers that opportunistically report progress still work.
        logger.debug("Dropping progress notification on unary gRPC transport")

    async def send_raw_request(
        self,
        method: str,
        params: Mapping[str, Any] | None,
        opts: CallOptions | None = None,
    ) -> dict[str, Any]:
        raise NoBackChannelError(method)

    async def notify(self, method: str, params: Mapping[str, Any] | None) -> None:
        # Server-to-client notifications are not supported on stateless unary gRPC.
        raise NoBackChannelError(method)


class McpServicer(mcp_pb2_grpc.McpServicer):
    """gRPC servicer mapping RPCs to MCP handlers.

    All translation happens directly between dicts and protos via `convert.py`;
    we deliberately avoid building intermediate Pydantic models because the
    SDK runner validates `params` before invoking the handler and validates
    the handler's result before returning it to us, so any Pydantic step here
    is redundant work.
    """

    def __init__(self):
        self._on_request: OnRequest | None = None
        self._on_notify: OnNotify | None = None

    def set_handlers(self, on_request: OnRequest | None, on_notify: OnNotify | None) -> None:
        self._on_request = on_request
        self._on_notify = on_notify

    def _get_context(self) -> GRPCDispatchContext:
        transport_ctx = TransportContext(kind="grpc", can_send_request=False)
        return GRPCDispatchContext(transport_ctx)

    async def _handle_rpc(
        self,
        method: str,
        params: dict[str, Any] | None,
        result_to_proto: Callable[[dict[str, Any]], Message],
        context: grpc.aio.ServicerContext,
    ) -> Message:
        # Snapshot the callback to avoid TOCTOU between the None-check and the call:
        # set_handlers(None, None) can race with an in-flight RPC during shutdown.
        on_request = self._on_request
        if on_request is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Server not ready")

        dctx = self._get_context()
        try:
            result_dict = await on_request(dctx, method, params)
            return result_to_proto(result_dict)
        except Exception as e:
            if not isinstance(e, MCPError):
                logger.exception("Internal error in RPC handler: %s", method)
            mcp_err = errors.exception_to_mcp_error(e)
            grpc_code, message, metadata = errors.mcp_error_to_grpc_status(mcp_err)
            await context.abort(grpc_code, message, metadata)

    async def ListTools(
        self,
        request: mcp_messages_pb2.ListToolsRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ListToolsResponse:
        params: dict[str, Any] = {}
        meta = convert.extract_meta(request)
        if meta is not None:
            params["_meta"] = meta
        return await self._handle_rpc(
            method="tools/list",
            params=params,
            result_to_proto=convert.list_tools_result_dict_to_proto,
            context=context,
        )

    async def CallTool(
        self,
        request: mcp_messages_pb2.CallToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.CallToolResponse:
        if not request.HasField("request") or not request.request.name:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing tool name")
            return mcp_messages_pb2.CallToolResponse()

        params = convert.call_tool_request_proto_to_params_dict(request)
        return await self._handle_rpc(
            method="tools/call",
            params=params,
            result_to_proto=convert.call_tool_result_dict_to_proto,
            context=context,
        )

    async def ListResources(
        self,
        request: mcp_messages_pb2.ListResourcesRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ListResourcesResponse:
        params: dict[str, Any] = {}
        meta = convert.extract_meta(request)
        if meta is not None:
            params["_meta"] = meta
        return await self._handle_rpc(
            method="resources/list",
            params=params,
            result_to_proto=convert.list_resources_result_dict_to_proto,
            context=context,
        )

    async def ListResourceTemplates(
        self,
        request: mcp_messages_pb2.ListResourceTemplatesRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ListResourceTemplatesResponse:
        params: dict[str, Any] = {}
        meta = convert.extract_meta(request)
        if meta is not None:
            params["_meta"] = meta
        return await self._handle_rpc(
            method="resources/templates/list",
            params=params,
            result_to_proto=convert.list_resource_templates_result_dict_to_proto,
            context=context,
        )

    async def ReadResource(
        self,
        request: mcp_messages_pb2.ReadResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ReadResourceResponse:
        if not request.uri:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing resource URI")
            return mcp_messages_pb2.ReadResourceResponse()

        params = convert.read_resource_request_proto_to_params_dict(request)
        return await self._handle_rpc(
            method="resources/read",
            params=params,
            result_to_proto=convert.read_resource_result_dict_to_proto,
            context=context,
        )


class GRPCServerDispatcher(Dispatcher[TransportContext]):
    """Server-side gRPC dispatcher."""

    def __init__(self, servicer: McpServicer):
        self.servicer = servicer
        self._close_event = anyio.Event()

    async def run(
        self,
        on_request: OnRequest,
        on_notify: OnNotify,
        *,
        task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        """Register handlers and park until closed."""
        self.servicer.set_handlers(on_request, on_notify)
        task_status.started()
        try:
            await self._close_event.wait()
        finally:
            self.servicer.set_handlers(None, None)

    def close(self):
        """Unblock run()."""
        self._close_event.set()

    async def send_raw_request(
        self,
        method: str,
        params: Mapping[str, Any] | None,
        opts: CallOptions | None = None,
    ) -> dict[str, Any]:
        raise NoBackChannelError(method)

    async def notify(self, method: str, params: Mapping[str, Any] | None) -> None:
        # Stateless unary gRPC cannot push notifications to the client.
        raise NoBackChannelError(method)


class McpGrpcServer:
    """Orchestrator for MCP gRPC server.

    Operates in two modes:

    * **Managed** — provide `address` (and optionally `credentials` / `options`);
      the orchestrator constructs and owns the underlying `grpc.aio.Server`.
    * **Unmanaged** — provide a pre-built `server`; the orchestrator only owns
      the runner loop and leaves the gRPC server lifecycle to the caller.
    """

    def __init__(
        self,
        mcp_server: Server | MCPServer,
        address: str | None = None,
        server: grpc.aio.Server | None = None,
        *,
        credentials: grpc.ServerCredentials | None = None,
        options: list[tuple[str, int | str]] | None = None,
    ):
        # MCPServer is the high-level public type but ServerRunner needs the
        # low-level Server; extract via the documented helper when present.
        if isinstance(mcp_server, MCPServer):
            self.mcp_server = mcp_server._lowlevel_server
        else:
            self.mcp_server = mcp_server
        self.address = address
        self.credentials = credentials

        self.external_server = server is not None
        if server is not None:
            self.grpc_server = server
        else:
            if address is None:
                raise ValueError("address is required in managed mode")
            self.grpc_server = grpc.aio.server(options=options)

        self.servicer = McpServicer()
        mcp_pb2_grpc.add_McpServicer_to_server(self.servicer, self.grpc_server)

        self.dispatcher = GRPCServerDispatcher(self.servicer)
        self._exit_stack = AsyncExitStack()
        self._tg: anyio.abc.TaskGroup | None = None
        self._runner: ServerRunner | None = None

    async def start(self) -> None:
        """Start the gRPC server (if managed) and the MCP runner."""
        # Bring the gRPC server up first so the wire is ready before we
        # register handlers. In managed mode we own the listening socket;
        # in unmanaged mode the caller is expected to have started it.
        if not self.external_server:
            if self.credentials is not None:
                self.grpc_server.add_secure_port(self.address, self.credentials)
            else:
                self.grpc_server.add_insecure_port(self.address)
            await self.grpc_server.start()

        lifespan_context = await self._exit_stack.enter_async_context(
            self.mcp_server.lifespan(self.mcp_server)
        )

        self._runner = ServerRunner(
            server=self.mcp_server,
            dispatcher=self.dispatcher,
            lifespan_state=lifespan_context,
            init_options=self.mcp_server.create_initialization_options(),
            has_standalone_channel=False,
            stateless=True,
        )

        self._tg = anyio.create_task_group()
        await self._exit_stack.enter_async_context(self._tg)
        await self._tg.start(self._runner.run)

    async def stop(self, grace: float | None = DEFAULT_STOP_GRACE_SECONDS) -> None:
        """Stop the MCP runner and (if managed) the gRPC server.

        Args:
            grace: Seconds to allow in-flight RPCs to complete before forcing
                shutdown. Defaults to DEFAULT_STOP_GRACE_SECONDS; pass None to
                terminate immediately.
        """
        if not self.external_server:
            await self.grpc_server.stop(grace)
        self.dispatcher.close()
        await self._exit_stack.aclose()

    async def wait_for_termination(self) -> None:
        """Wait for the gRPC server to terminate."""
        await self.grpc_server.wait_for_termination()

    async def __aenter__(self) -> "McpGrpcServer":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
