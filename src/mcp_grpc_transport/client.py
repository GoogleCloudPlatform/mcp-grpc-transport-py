"""Client-side gRPC transport for MCP."""

import anyio
import anyio.abc
from collections.abc import Mapping
import logging
from typing import Any

import grpc
from mcp.shared.dispatcher import CallOptions, Dispatcher, OnNotify, OnRequest
from mcp.shared.exceptions import MCPError, NoBackChannelError
from mcp.shared.transport_context import TransportContext
import mcp.types as mcp_types
from pydantic import ValidationError

from mcp_grpc_transport import convert
from mcp_grpc_transport import errors
from mcp_grpc_transport_proto import mcp_messages_pb2
from mcp_grpc_transport_proto import mcp_pb2_grpc

logger = logging.getLogger(__name__)

class GRPCClientDispatcher(Dispatcher[TransportContext]):
    """Client-side gRPC dispatcher for MCP."""

    def __init__(
        self,
        address: str,
        channel: grpc.aio.Channel | None = None,
        *,
        credentials: grpc.ChannelCredentials | None = None,
        options: list[tuple[str, int | str]] | None = None,
        **grpc_channel_args
    ):
        """Initialize the client dispatcher.

        If `channel` is provided, it operates in external mode and uses this channel.
        If `channel` is NOT provided, it creates a new channel using `address` and `grpc_channel_args`.
        """
        self.address = address
        self.external_channel = channel is not None
        
        if channel:
            self.channel = channel
        else:
            if credentials:
                self.channel = grpc.aio.secure_channel(
                    address,
                    credentials,
                    options=options,
                    **grpc_channel_args
                )
            else:
                self.channel = grpc.aio.insecure_channel(
                    address,
                    options=options,
                    **grpc_channel_args
                )
                
        self.stub = mcp_pb2_grpc.McpStub(self.channel)
        self._close_event = anyio.Event()
        self._closed = False

    async def run(
        self,
        on_request: OnRequest,
        on_notify: OnNotify,
        *,
        task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        """Drive the client dispatcher.

        Since this is a client-side unary transport, it has no receive loop.
        It calls `task_status.started()` and blocks until `close()` is called.
        
        Using a try-finally block ensures that if the runner task group is 
        cancelled during teardown, close() is called to release the managed channel.
        """
        task_status.started()
        try:
            await self._close_event.wait()
        finally:
            await self.close()

    async def close(self) -> None:
        """Close the dispatcher."""
        self._close_event.set()
        # Ensure we only close the channel once (idempotent), avoiding double-close 
        # when called both explicitly and from run()'s finally block.
        if not self.external_channel and not self._closed:
            self._closed = True
            logger.info("Closing managed gRPC channel")
            await self.channel.close()

    async def send_raw_request(
        self,
        method: str,
        params: Mapping[str, Any] | None,
        opts: CallOptions | None = None,
    ) -> dict[str, Any]:
        """Send a request to the server and await the result."""
        # gRPC unary transport is fully stateless and does not negotiate version/handshake
        # over the wire. However, ClientSession requires initialize() to complete
        # to proceed. We mock the handshake locally by returning a mock InitializeResult.
        if method == "initialize":
            return {
                "protocolVersion": mcp_types.LATEST_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    "resources": {},
                },
                "serverInfo": {
                    "name": "gRPC-Client-Dispatcher",
                    "version": "0.1.0"
                }
            }

        # Map method name to stub RPC method
        if method == "tools/list":
            rpc_method = self.stub.ListTools
            request_proto = mcp_messages_pb2.ListToolsRequest()
            timeout = opts.get("timeout") if opts else None
            
            try:
                response_proto = await rpc_method(request_proto, timeout=timeout)
                result_obj = convert.list_tools_result_from_proto(response_proto)
                return result_obj.model_dump(by_alias=True, exclude_none=True)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, "Error during ListTools")
                
        elif method == "tools/call":
            rpc_method = self.stub.CallTool
            assert params is not None, "tools/call requires params"
            try:
                mcp_params = mcp_types.CallToolRequestParams.model_validate(params)
            except ValidationError as e:
                raise MCPError(
                    code=mcp_types.INVALID_PARAMS,
                    message=f"Invalid params for tools/call: {e}"
                )
                
            request_proto = convert.call_tool_params_to_proto(mcp_params)
            timeout = opts.get("timeout") if opts else None
            
            try:
                response_proto = await rpc_method(request_proto, timeout=timeout)
                result_obj = convert.call_tool_result_from_proto(response_proto)
                return result_obj.model_dump(by_alias=True, exclude_none=True)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, f"Error during CallTool for tool {mcp_params.name}")
                
        elif method == "resources/list":
            rpc_method = self.stub.ListResources
            request_proto = mcp_messages_pb2.ListResourcesRequest()
            timeout = opts.get("timeout") if opts else None
            try:
                response_proto = await rpc_method(request_proto, timeout=timeout)
                result_obj = convert.list_resources_result_from_proto(response_proto)
                return result_obj.model_dump(by_alias=True, exclude_none=True)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, "Error during ListResources")
                
        elif method == "resources/templates/list":
            rpc_method = self.stub.ListResourceTemplates
            request_proto = mcp_messages_pb2.ListResourceTemplatesRequest()
            timeout = opts.get("timeout") if opts else None
            try:
                response_proto = await rpc_method(request_proto, timeout=timeout)
                result_obj = convert.list_resource_templates_result_from_proto(response_proto)
                return result_obj.model_dump(by_alias=True, exclude_none=True)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, "Error during ListResourceTemplates")
                
        elif method == "resources/read":
            rpc_method = self.stub.ReadResource
            assert params is not None, "resources/read requires params"
            try:
                mcp_params = mcp_types.ReadResourceRequestParams.model_validate(params)
            except ValidationError as e:
                raise MCPError(
                    code=mcp_types.INVALID_PARAMS,
                    message=f"Invalid params for resources/read: {e}"
                )
            request_proto = convert.read_resource_request_params_to_proto(mcp_params)
            timeout = opts.get("timeout") if opts else None
            try:
                response_proto = await rpc_method(request_proto, timeout=timeout)
                result_obj = convert.read_resource_result_from_proto(response_proto)
                return result_obj.model_dump(by_alias=True, exclude_none=True)
            except grpc.aio.AioRpcError as e:
                raise errors.grpc_error_to_mcp_error(e, f"Error during ReadResource for {mcp_params.uri}")
                
        else:
            raise MCPError(
                code=mcp_types.METHOD_NOT_FOUND,
                message=f"Method not found: {method}"
            )

    async def notify(self, method: str, params: Mapping[str, Any] | None) -> None:
        """Send a notification."""
        if method == "notifications/initialized":
            logger.debug("Dropping notifications/initialized for gRPC transport")
            return
            
        raise NoBackChannelError(method)
