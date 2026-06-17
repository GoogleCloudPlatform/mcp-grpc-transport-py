"""Server-side gRPC transport for MCP."""

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
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
import mcp.types as mcp_types
from mcp.types import RequestId
from google.protobuf import json_format
from pydantic import BaseModel, ValidationError

from mcp_grpc_transport import convert
from mcp_grpc_transport import errors
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc

logger = logging.getLogger(__name__)

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
        # gRPC unary transport is stateless and does not support server-initiated requests (no backchannel).
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
        pass

    async def send_raw_request(
        self,
        method: str,
        params: Mapping[str, Any] | None,
        opts: CallOptions | None = None,
    ) -> dict[str, Any]:
        # Server-to-client requests are not supported on stateless gRPC transport.
        raise NoBackChannelError(method)

    async def notify(self, method: str, params: Mapping[str, Any] | None) -> None:
        pass


class McpServicer(mcp_pb2_grpc.McpServicer):
    """gRPC servicer mapping RPCs to MCP handlers."""

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
        result_model: type[BaseModel],
        response_converter: Callable[[BaseModel], Message],
        context: grpc.aio.ServicerContext,
    ) -> Message:
        if not self._on_request:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Server not ready")
            
        dctx = self._get_context()
        try:
            # Dispatch incoming request to SDK ServerRunner which returns a raw dict response.
            result_dict = await self._on_request(dctx, method, params)
            # Validate raw dict into expected Pydantic model. Pydantic handles automatic
            # translation of camelCase wire fields into snake_case properties on result_obj.
            result_obj = result_model.model_validate(result_dict)
            # Convert python Pydantic object back into equivalent Protobuf message.
            return response_converter(result_obj)
        except MCPError as e:
            grpc_code, message = errors.mcp_error_to_grpc_status(e)
            await context.abort(grpc_code, message)
        except Exception as e:
            logger.exception("Internal error in RPC handler: %s", method)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def ListTools(
        self,
        request: mcp_messages_pb2.ListToolsRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ListToolsResponse:
        params_dict = {}
        if request.HasField("common") and request.common.HasField("metadata"):
            params_dict["_meta"] = convert.struct_to_dict(request.common.metadata)
            
        return await self._handle_rpc(
            method="tools/list",
            params=params_dict,
            result_model=mcp_types.ListToolsResult,
            response_converter=convert.list_tools_result_to_proto,
            context=context,
        )

    async def CallTool(
        self,
        request: mcp_messages_pb2.CallToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.CallToolResponse:
        if not request.HasField("request") or not request.request.name:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing tool name")
            
        try:
            mcp_params = convert.call_tool_params_from_proto(request)
            params_dict = mcp_params.model_dump(by_alias=True, exclude_none=True)
            if request.HasField("common") and request.common.HasField("metadata"):
                params_dict["_meta"] = convert.struct_to_dict(request.common.metadata)
        except (ValidationError, json_format.ParseError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid request: {e}")
            
        return await self._handle_rpc(
            method="tools/call",
            params=params_dict,
            result_model=mcp_types.CallToolResult,
            response_converter=convert.call_tool_result_to_proto,
            context=context,
        )

    async def ListResources(
        self,
        request: mcp_messages_pb2.ListResourcesRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ListResourcesResponse:
        params_dict = {}
        if request.HasField("common") and request.common.HasField("metadata"):
            params_dict["_meta"] = convert.struct_to_dict(request.common.metadata)
            
        return await self._handle_rpc(
            method="resources/list",
            params=params_dict,
            result_model=mcp_types.ListResourcesResult,
            response_converter=convert.list_resources_result_to_proto,
            context=context,
        )

    async def ListResourceTemplates(
        self,
        request: mcp_messages_pb2.ListResourceTemplatesRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ListResourceTemplatesResponse:
        params_dict = {}
        if request.HasField("common") and request.common.HasField("metadata"):
            params_dict["_meta"] = convert.struct_to_dict(request.common.metadata)
            
        return await self._handle_rpc(
            method="resources/templates/list",
            params=params_dict,
            result_model=mcp_types.ListResourceTemplatesResult,
            response_converter=convert.list_resource_templates_result_to_proto,
            context=context,
        )

    async def ReadResource(
        self,
        request: mcp_messages_pb2.ReadResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> mcp_messages_pb2.ReadResourceResponse:
        if not request.uri:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing resource URI")
            
        try:
            mcp_params = convert.read_resource_request_params_from_proto(request)
            params_dict = mcp_params.model_dump(by_alias=True, exclude_none=True)
            if request.HasField("common") and request.common.HasField("metadata"):
                params_dict["_meta"] = convert.struct_to_dict(request.common.metadata)
        except (ValidationError, json_format.ParseError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid request: {e}")
            
        return await self._handle_rpc(
            method="resources/read",
            params=params_dict,
            result_model=mcp_types.ReadResourceResult,
            response_converter=convert.read_resource_result_to_proto,
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
        pass


class McpGrpcServer:
    """Orchestrator for MCP gRPC server."""

    def __init__(
        self,
        mcp_server: Server | MCPServer,
        address: str | None = None,
        server: grpc.aio.Server | None = None,
        *,
        credentials: grpc.ServerCredentials | None = None,
        options: list[tuple[str, int | str]] | None = None,
        **grpc_server_args
    ):
        # Allow passing either a low-level Server or a high-level MCPServer.
        # We extract the underlying low-level Server (via _lowlevel_server) because
        # the SDK's ServerRunner strictly requires the low-level Server class to operate.
        if hasattr(mcp_server, "_lowlevel_server"):
            self.mcp_server = mcp_server._lowlevel_server
        else:
            self.mcp_server = mcp_server
        self.address = address
        self.credentials = credentials
        
        self.external_server = server is not None
        if server:
            self.grpc_server = server
        else:
            if address is None:
                raise ValueError("address is required in managed mode")
            self.grpc_server = grpc.aio.server(options=options, **grpc_server_args)
            
        self.servicer = McpServicer()
        mcp_pb2_grpc.add_McpServicer_to_server(self.servicer, self.grpc_server)
        
        self.dispatcher = GRPCServerDispatcher(self.servicer)
        self._exit_stack = AsyncExitStack()
        self._tg = None
        self._runner = None

    async def start(self):
        """Start the MCP runner and the gRPC server (if managed)."""
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
        
        # Start runner in background task group
        self._tg = anyio.create_task_group()
        await self._exit_stack.enter_async_context(self._tg)
        # We cast dispatcher to Any because ServerRunner type-hints JSONRPCDispatcher
        # and we use a custom Dispatcher implementation.
        await self._tg.start(self._runner.run)
        
        # Start server if managed
        if not self.external_server:
            if self.credentials:
                self.grpc_server.add_secure_port(self.address, self.credentials)
            else:
                self.grpc_server.add_insecure_port(self.address)
            await self.grpc_server.start()

    async def stop(self, grace: float | None = None):
        """Stop the gRPC server (if managed) and the MCP runner."""
        if not self.external_server:
            await self.grpc_server.stop(grace)
        self.dispatcher.close()
        await self._exit_stack.aclose()

    async def wait_for_termination(self):
        """Wait for the gRPC server to terminate."""
        await self.grpc_server.wait_for_termination()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
