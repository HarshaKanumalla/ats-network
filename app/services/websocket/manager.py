from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, List, Optional
import logging
import asyncio
import json
from datetime import datetime

from ...core.exceptions import WebSocketError
from ...core.auth.token import token_service
from ...services.notification.notification_service import notification_service
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class WebSocketManager:
    def __init__(self):
        """Initialize WebSocket manager."""
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.connection_states: Dict[str, Dict[str, Any]] = {}
        self.reconnection_attempts: Dict[str, int] = {}
        self.message_buffers: Dict[str, List[Dict[str, Any]]] = {}
        self.lock = asyncio.Lock()  # Ensure thread-safe access to shared data
        
        self.settings = {
            'max_reconnect_attempts': 5,
            'reconnect_delay': 1000,  # milliseconds
            'heartbeat_interval': 30,  # seconds
            'connection_timeout': 60,  # seconds
            'message_buffer_size': 100,
            'max_clients_per_session': 5
        }
        
        logger.info("WebSocket manager initialized")

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        token: str
    ) -> str:
        """Establish new WebSocket connection with authentication."""
        try:
            # Validate authentication token
            token_data = await token_service.validate_access_token(token)
            if not token_data:
                raise WebSocketError("Invalid authentication token")

            # Generate unique client identifier
            client_id = f"client_{token_data['sub']}_{datetime.utcnow().timestamp()}"

            # Check client limit for session
            async with self.lock:
                if (session_id in self.active_connections and 
                    len(self.active_connections[session_id]) >= self.settings['max_clients_per_session']):
                    raise WebSocketError("Maximum clients reached for session")

                # Accept connection
                await websocket.accept()

                # Initialize session tracking
                if session_id not in self.active_connections:
                    self.active_connections[session_id] = {}
                    self.message_buffers[session_id] = []

                # Store connection
                self.active_connections[session_id][client_id] = websocket
                
                # Initialize connection state
                self.connection_states[client_id] = {
                    'connected': True,
                    'last_heartbeat': datetime.utcnow(),
                    'session_id': session_id,
                    'user_id': token_data['sub']
                }

            # Start monitoring tasks
            asyncio.create_task(self._monitor_heartbeat(session_id, client_id))
            asyncio.create_task(self._monitor_connection_timeout(session_id, client_id))

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
            logger.error(f"Connection error: {str(e)}")
            raise WebSocketError(f"Connection failed: {str(e)}")

    async def _send_buffered_messages(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Send buffered messages to a reconnected client."""
        try:
            async with self.lock:
                if session_id in self.message_buffers:
                    for message in self.message_buffers[session_id]:
                        websocket = self.active_connections[session_id].get(client_id)
                        if websocket:
                            await self._send_message(websocket, message)
        except Exception as e:
            logger.error(f"Error sending buffered messages: {str(e)}")

    async def _send_message(
        self,
        websocket: WebSocket,
        message: Dict[str, Any]
    ) -> None:
        """Send a message to a WebSocket client."""
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            raise WebSocketError("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            raise WebSocketError(f"Failed to send message: {str(e)}")

    async def _broadcast_to_session(
        self,
        session_id: str,
        message: Dict[str, Any]
    ) -> None:
        """Send message to all clients in a session."""
        async with self.lock:
            if session_id not in self.active_connections:
                return

            disconnected_clients = []
            for client_id, websocket in self.active_connections[session_id].items():
                try:
                    await self._send_message(websocket, message)
                except WebSocketError:
                    disconnected_clients.append(client_id)

            # Clean up disconnected clients
            for client_id in disconnected_clients:
                await self._handle_disconnect(session_id, client_id)

    async def _handle_disconnect(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Handle client disconnection."""
        async with self.lock:
            if session_id in self.active_connections:
                if client_id in self.active_connections[session_id]:
                    del self.active_connections[session_id][client_id]
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]
                    del self.message_buffers[session_id]

            if client_id in self.connection_states:
                del self.connection_states[client_id]

            if client_id in self.reconnection_attempts:
                del self.reconnection_attempts[client_id]

            logger.info(f"Cleaned up connection for client {client_id}")

# Initialize WebSocket manager
websocket_manager = WebSocketManager()