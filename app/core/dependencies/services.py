# backend/app/core/dependencies/services.py

from fastapi import Depends
from typing import Annotated
from ..services import (
    DatabaseManager,
    CacheService,
    AuthenticationService,
    NotificationService
)

db = DatabaseManager()
cache = CacheService()
auth = AuthenticationService()
notifications = NotificationService()

def get_db():
    return db

def get_cache():
    return cache

def get_auth():
    return auth

def get_notifications():
    return notifications

# Type annotations for cleaner dependency injection
DBDependency = Annotated[DatabaseManager, Depends(get_db)]
CacheDependency = Annotated[CacheService, Depends(get_cache)]
AuthDependency = Annotated[AuthenticationService, Depends(get_auth)]
NotificationDependency = Annotated[NotificationService, Depends(get_notifications)]