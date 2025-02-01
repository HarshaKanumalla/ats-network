# backend/app/services/websocket/manager.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Set, Optional
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
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.connection_states: Dict[str, Dict[str, Any]] = {}
        self.reconnection_attempts: Dict[str, int] = {}
        self.message_buffers: Dict[str, List[Dict[str, Any]]] = {}
        
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
            raise WebSocketError(f"Failed to broadcast data: {str(e)}")

    async def _broadcast_to_session(
        self,
        session_id: str,
        message: Dict[str, Any]
    ) -> None:
        """Send message to all clients in a session."""
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
            await self._handle_disconnect(session_id, client_id)

    async def _handle_disconnect(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Handle client disconnection with reconnection support."""
        try:
            # Update connection state
            if client_id in self.connection_states:
                self.connection_states[client_id]['connected'] = False
                
            # Attempt reconnection if within limits
            reconnect_count = self.reconnection_attempts.get(client_id, 0)
            if reconnect_count < self.settings['max_reconnect_attempts']:
                self.reconnection_attempts[client_id] = reconnect_count + 1
                await self._attempt_reconnection(session_id, client_id)
            else:
                await self._cleanup_connection(session_id, client_id)
                
            logger.info(f"Client {client_id} disconnected from session {session_id}")

        except Exception as e:
            logger.error(f"Disconnect handling error: {str(e)}")
            await self._cleanup_connection(session_id, client_id)

    async def _attempt_reconnection(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Attempt to reconnect client with exponential backoff."""
        try:
            reconnect_count = self.reconnection_attempts[client_id]
            delay = self.settings['reconnect_delay'] * (2 ** (reconnect_count - 1))
            
            await asyncio.sleep(delay / 1000)  # Convert to seconds
            
            if client_id in self.connection_states:
                # Create new connection
                new_websocket = await self._establish_new_connection(
                    session_id,
                    client_id
                )
                
                if new_websocket:
                    self.active_connections[session_id][client_id] = new_websocket
                    self.connection_states[client_id]['connected'] = True
                    self.reconnection_attempts[client_id] = 0
                    
                    # Resume session
                    await self._resume_session(session_id, client_id)
                    
                    logger.info(f"Successfully reconnected client {client_id}")

        except Exception as e:
            logger.error(f"Reconnection attempt failed: {str(e)}")

    async def _start_monitoring_tasks(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Start connection monitoring tasks."""
        asyncio.create_task(
            self._monitor_heartbeat(session_id, client_id)
        )
        asyncio.create_task(
            self._monitor_connection_timeout(session_id, client_id)
        )

    async def _monitor_heartbeat(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Monitor connection health through heartbeat mechanism."""
        while self.connection_states.get(client_id, {}).get('connected', False):
            try:
                await asyncio.sleep(self.settings['heartbeat_interval'])
                
                if client_id in self.connection_states:
                    last_heartbeat = self.connection_states[client_id]['last_heartbeat']
                    time_since_heartbeat = (
                        datetime.utcnow() - last_heartbeat
                    ).total_seconds()
                    
                    if time_since_heartbeat > self.settings['heartbeat_interval'] * 2:
                        await self._handle_disconnect(session_id, client_id)
                        break

            except Exception as e:
                logger.error(f"Heartbeat monitoring error: {str(e)}")

    async def _monitor_connection_timeout(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Monitor overall connection timeout."""
        try:
            await asyncio.sleep(self.settings['connection_timeout'])
            
            if client_id in self.connection_states:
                if not self.connection_states[client_id]['connected']:
                    await self._cleanup_connection(session_id, client_id)

        except Exception as e:
            logger.error(f"Connection timeout monitoring error: {str(e)}")

    async def _cleanup_connection(
        self,
        session_id: str,
        client_id: str
    ) -> None:
        """Clean up connection resources."""
        try:
            if session_id in self.active_connections:
                if client_id in self.active_connections[session_id]:
                    del self.active_connections[session_id][client_id]
                
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]
                    if session_id in self.message_buffers:
                        del self.message_buffers[session_id]

            if client_id in self.connection_states:
                del self.connection_states[client_id]

            if client_id in self.reconnection_attempts:
                del self.reconnection_attempts[client_id]

            logger.info(f"Cleaned up connection for client {client_id}")

        except Exception as e:
            logger.error(f"Connection cleanup error: {str(e)}")

# Initialize WebSocket manager
websocket_manager = WebSocketManager()