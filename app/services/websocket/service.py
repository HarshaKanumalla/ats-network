# backend/app/services/websocket/service.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Set, Optional
import logging
import asyncio
import json
from datetime import datetime

from ...core.exceptions import WebSocketError
from ...core.auth.token import TokenService
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.session_clients: Dict[str, Set[str]] = {}
        self.token_service = TokenService()
        
        # Connection management settings
        self.heartbeat_interval = 30  # seconds
        self.connection_timeout = 60  # seconds
        self.max_reconnect_attempts = 3
        
        # Message buffering
        self.message_buffer_size = 100
        self.message_buffers: Dict[str, list] = {}
        
        logger.info("WebSocket manager initialized")

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        token: str
    ) -> str:
        """Establish new WebSocket connection with proper authentication and validation."""
        try:
            # Validate token
            token_data = await self.token_service.validate_access_token(token)
            if not token_data:
                raise WebSocketError("Invalid authentication token")

            # Generate unique client identifier
            client_id = f"client_{token_data['sub']}_{datetime.utcnow().timestamp()}"

            # Accept connection
            await websocket.accept()

            # Initialize session tracking
            if session_id not in self.active_connections:
                self.active_connections[session_id] = {}
                self.session_clients[session_id] = set()
                self.message_buffers[session_id] = []

            # Store connection
            self.active_connections[session_id][client_id] = websocket
            self.session_clients[session_id].add(client_id)

            # Start connection monitoring
            asyncio.create_task(self._monitor_connection(session_id, client_id))

            # Send connection acknowledgment
            await self._send_message(
                websocket,
                {
                    "type": "connection_established",
                    "client_id": client_id,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            # Send buffered messages
            await self._send_buffered_messages(session_id, client_id)

            logger.info(f"Client {client_id} connected to session {session_id}")
            return client_id

        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            raise WebSocketError(f"Connection failed: {str(e)}")

    async def disconnect(self, session_id: str, client_id: str) -> None:
        """Handle client disconnection with proper cleanup."""
        try:
            if session_id in self.active_connections:
                if client_id in self.active_connections[session_id]:
                    del self.active_connections[session_id][client_id]
                    self.session_clients[session_id].discard(client_id)

                # Clean up empty session
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]
                    del self.session_clients[session_id]
                    del self.message_buffers[session_id]

            await self._log_disconnection(session_id, client_id)
            logger.info(f"Client {client_id} disconnected from session {session_id}")

        except Exception as e:
            logger.error(f"Disconnection handling error: {str(e)}")

    async def broadcast_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any]
    ) -> None:
        """Broadcast test data to all connected clients in a session."""
        try:
            message = {
                "type": "test_data",
                "test_type": test_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Buffer message
            await self._buffer_message(session_id, message)

            # Broadcast to all connected clients
            disconnected_clients = []
            
            if session_id in self.active_connections:
                for client_id, websocket in self.active_connections[session_id].items():
                    try:
                        await self._send_message(websocket, message)
                    except WebSocketDisconnect:
                        disconnected_clients.append(client_id)
                    except Exception as e:
                        logger.error(f"Broadcast error for client {client_id}: {str(e)}")
                        disconnected_clients.append(client_id)

            # Clean up disconnected clients
            for client_id in disconnected_clients:
                await self.disconnect(session_id, client_id)

        except Exception as e:
            logger.error(f"Test data broadcast error: {str(e)}")
            raise WebSocketError(f"Failed to broadcast test data: {str(e)}")

    async def _monitor_connection(self, session_id: str, client_id: str) -> None:
        """Monitor connection health and handle timeouts."""
        try:
            while session_id in self.active_connections and \
                  client_id in self.active_connections[session_id]:
                
                websocket = self.active_connections[session_id][client_id]
                
                try:
                    # Send heartbeat
                    await self._send_message(
                        websocket,
                        {"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()}
                    )
                    
                    # Wait for response
                    response = await websocket.receive_text()
                    if json.loads(response).get("type") != "heartbeat_ack":
                        raise WebSocketError("Invalid heartbeat response")

                except Exception as e:
                    logger.warning(f"Connection monitoring error: {str(e)}")
                    await self.disconnect(session_id, client_id)
                    break

                await asyncio.sleep(self.heartbeat_interval)

        except Exception as e:
            logger.error(f"Connection monitoring error: {str(e)}")
            await self.disconnect(session_id, client_id)

    async def _buffer_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Buffer messages for reconnecting clients."""
        if session_id not in self.message_buffers:
            self.message_buffers[session_id] = []

        buffer = self.message_buffers[session_id]
        buffer.append(message)

        # Maintain buffer size
        if len(buffer) > self.message_buffer_size:
            buffer.pop(0)

    async def _send_buffered_messages(self, session_id: str, client_id: str) -> None:
        """Send buffered messages to newly connected or reconnected client."""
        if session_id in self.message_buffers and \
           session_id in self.active_connections and \
           client_id in self.active_connections[session_id]:
            
            websocket = self.active_connections[session_id][client_id]
            for message in self.message_buffers[session_id]:
                await self._send_message(websocket, message)

    async def _log_disconnection(self, session_id: str, client_id: str) -> None:
        """Log client disconnection for monitoring."""
        try:
            await db_manager.execute_query(
                collection="connection_logs",
                operation="insert_one",
                query={
                    "session_id": session_id,
                    "client_id": client_id,
                    "event": "disconnection",
                    "timestamp": datetime.utcnow()
                }
            )
        except Exception as e:
            logger.error(f"Failed to log disconnection: {str(e)}")

# Initialize WebSocket manager
websocket_manager = WebSocketManager()