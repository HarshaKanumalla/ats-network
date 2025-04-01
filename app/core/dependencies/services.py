# backend/app/core/dependencies/services.py

from fastapi import Depends
from typing import Annotated
from contextlib import asynccontextmanager
import logging

from ..services import (
    DatabaseManager,
    CacheService,
    AuthenticationService,
    NotificationService
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db() -> DatabaseManager:
    """Provide a new instance of DatabaseManager with proper cleanup."""
    db = DatabaseManager()
    try:
        logger.info("Initializing DatabaseManager")
        yield db
    finally:
        logger.info("Closing DatabaseManager")
        await db.close()

@asynccontextmanager
async def get_cache() -> CacheService:
    """Provide a new instance of CacheService with proper cleanup."""
    cache = CacheService()
    try:
        logger.info("Initializing CacheService")
        yield cache
    finally:
        logger.info("Closing CacheService")
        await cache.close()

@asynccontextmanager
async def get_auth() -> AuthenticationService:
    """Provide a new instance of AuthenticationService."""
    auth = AuthenticationService()
    try:
        logger.info("Initializing AuthenticationService")
        yield auth
    finally:
        logger.info("Cleaning up AuthenticationService")

@asynccontextmanager
async def get_notifications() -> NotificationService:
    """Provide a new instance of NotificationService."""
    notifications = NotificationService()
    try:
        logger.info("Initializing NotificationService")
        yield notifications
    finally:
        logger.info("Cleaning up NotificationService")

# Type annotations for cleaner dependency injection
DBDependency = Annotated[DatabaseManager, Depends(get_db)]
CacheDependency = Annotated[CacheService, Depends(get_cache)]
AuthDependency = Annotated[AuthenticationService, Depends(get_auth)]
NotificationDependency = Annotated[NotificationService, Depends(get_notifications)]