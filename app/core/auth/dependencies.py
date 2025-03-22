# backend/app/core/auth/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
import logging

from .manager import auth_manager
from .rbac import rbac_system
from ..exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency for getting current authenticated user."""
    try:
        return await auth_manager.get_user_from_token(token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )

async def get_current_active_user(
    current_user = Depends(get_current_user)
):
    """Dependency for getting current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user

def require_permissions(permissions: List[str]):
    """Dependency factory for requiring specific permissions."""
    async def permission_dependency(
        current_user = Depends(get_current_active_user)
    ):
        for permission in permissions:
            if not await rbac_system.verify_permission(
                str(current_user.id),
                permission
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {permission}"
                )
        return current_user
    return permission_dependency

def require_role(allowed_roles: List[str]):
    """Dependency factory for requiring specific roles."""
    async def role_dependency(
        current_user = Depends(get_current_active_user)
    ):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not authorized"
            )
        return current_user
    return role_dependency