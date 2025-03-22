# backend/app/services/websocket/service.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Set, Optional
import logging
import asyncio
import json
from datetime import datetime
from bson import ObjectId

from ...core.exceptions import WebSocketError
from ...core.auth.token import token_service
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class WebSocketManager:
    """Enhanced service for managing WebSocket connections and real-time data."""
    
    def __init__(self):
        """Initialize WebSocket manager with enhanced features."""
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.session_clients: Dict[str, Set[str]] = {}
        self.connection_states: Dict[str, Dict[str, Any]] = {}
        
        # Connection monitoring settings
        self.monitoring_settings = {
            'heartbeat_interval': 30,     # seconds
            'connection_timeout': 60,     # seconds
            'max_reconnect_attempts': 3,
            'reconnect_delay': 1000,      # milliseconds
            'message_buffer_size': 100,
            'max_clients_per_session': 5
        }
        
        # Message types and handlers
        self.message_handlers = {
            'test_data': self._handle_test_data,
            'status_update': self._handle_status_update,
            'alert': self._handle_alert,
            'heartbeat': self._handle_heartbeat
        }
        
        # Message buffering
        self.message_buffers: Dict[str, list] = {}
        
        logger.info("WebSocket manager initialized with enhanced features")

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
            if (session_id in self.active_connections and 
                len(self.active_connections[session_id]) >= 
                self.monitoring_settings['max_clients_per_session']):
                raise WebSocketError("Maximum clients reached for session")

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
            
            # Initialize connection state
            self.connection_states[client_id] = {
                'connected': True,
                'last_heartbeat': datetime.utcnow(),
                'session_id': session_id,
                'user_id': token_data['sub']
            }

            # Start monitoring tasks
            await self._start_monitoring_tasks(session_id, client_id)

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

            # Buffer message for recovery
            await self._buffer_message(session_id, message)

            # Broadcast to connected clients
            await self._broadcast_to_session(session_id, message)

        except Exception as e:
            logger.error(f"Broadcast error: {str(e)}")
            raise WebSocketError("Failed to broadcast test data")

    async def disconnect_client(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Handle client disconnection with cleanup."""
        try:
            if session_id in self.active_connections:
                if client_id in self.active_connections[session_id]:
                    websocket = self.active_connections[session_id][client_id]
                    await websocket.close()
                    del self.active_connections[session_id][client_id]
                    self.session_clients[session_id].discard(client_id)

                # Clean up empty session
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]
                    del self.session_clients[session_id]
                    del self.message_buffers[session_id]

            # Update connection state
            if client_id in self.connection_states:
                self.connection_states[client_id]['connected'] = False

            await self._log_disconnection(session_id, client_id)
            logger.info(f"Client {client_id} disconnected from session {session_id}")

        except Exception as e:
            logger.error(f"Disconnection error: {str(e)}")

    async def _start_monitoring_tasks(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Start connection monitoring tasks."""
        asyncio.create_task(
            self._monitor_connection(session_id, client_id)
        )
        asyncio.create_task(
            self._monitor_heartbeat(session_id, client_id)
        )

    async def _monitor_connection(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Monitor connection health and handle timeouts."""
        try:
            while session_id in self.active_connections and \
                  client_id in self.active_connections[session_id]:
                
                websocket = self.active_connections[session_id][client_id]
                
                try:
                    # Send heartbeat
                    await self._send_message(
                        websocket,
                        {
                            "type": "heartbeat",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
                    
                    # Wait for response
                    response = await websocket.receive_json()
                    if response.get("type") != "heartbeat_ack":
                        raise WebSocketError("Invalid heartbeat response")

                except Exception as e:
                    logger.warning(f"Connection monitoring error: {str(e)}")
                    await self.disconnect_client(session_id, client_id)
                    break

                await asyncio.sleep(self.monitoring_settings['heartbeat_interval'])

        except Exception as e:
            logger.error(f"Connection monitoring error: {str(e)}")
            await self.disconnect_client(session_id, client_id)

    async def _buffer_message(
        self,
        session_id: str,
        message: Dict[str, Any]
    ) -> None:
        """Buffer messages for recovery."""
        if session_id not in self.message_buffers:
            self.message_buffers[session_id] = []

        buffer = self.message_buffers[session_id]
        buffer.append(message)

        # Maintain buffer size
        if len(buffer) > self.monitoring_settings['message_buffer_size']:
            buffer.pop(0)

    async def _send_buffered_messages(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Send buffered messages to reconnected client."""
        if session_id in self.message_buffers and \
           session_id in self.active_connections and \
           client_id in self.active_connections[session_id]:
            
            websocket = self.active_connections[session_id][client_id]
            for message in self.message_buffers[session_id]:
                await self._send_message(websocket, message)

    async def _broadcast_to_session(
        self,
        session_id: str,
        message: Dict[str, Any]
    ) -> None:
        """Broadcast message to all clients in a session."""
        if session_id not in self.active_connections:
            return

        disconnected_clients = []
        for client_id, websocket in self.active_connections[session_id].items():
            try:
                await self._send_message(websocket, message)
            except Exception:
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect_client(session_id, client_id)

    async def _send_message(
        self,
        websocket: WebSocket,
        message: Dict[str, Any]
    ) -> None:
        """Send message with retry mechanism."""
        for attempt in range(self.monitoring_settings['max_reconnect_attempts']):
            try:
                await websocket.send_json(message)
                return
            except Exception as e:
                if attempt == self.monitoring_settings['max_reconnect_attempts'] - 1:
                    raise WebSocketError(f"Failed to send message: {str(e)}")
                await asyncio.sleep(
                    self.monitoring_settings['reconnect_delay'] / 1000
                )

    async def _log_disconnection(
        self,
        session_id: str,
        client_id: str
    ) -> None:
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