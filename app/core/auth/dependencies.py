# backend/app/core/auth/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
import logging

from .manager import auth_manager
from .rbac import rbac_system
from ..exceptions import AuthenticationError, AuthorizationError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Configurable token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=settings.TOKEN_URL or "api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependency for getting the current authenticated user.

    Args:
        token (str): The OAuth2 token provided by the client.

    Returns:
        User: The authenticated user object.

    Raises:
        HTTPException: If authentication fails.
    """
    try:
        user = await auth_manager.get_user_from_token(token)
        logger.info(f"User {user.id} authenticated successfully.")
        return user
    except AuthenticationError as e:
        logger.warning(f"Authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_active_user(current_user=Depends(get_current_user)):
    """
    Dependency for getting the current active user.

    Args:
        current_user: The authenticated user object.

    Returns:
        User: The active user object.

    Raises:
        HTTPException: If the user is inactive.
    """
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    logger.info(f"Active user {current_user.id} authorized successfully.")
    return current_user


def require_permissions(permissions: List[str]):
    """
    Dependency factory for requiring specific permissions.

    Args:
        permissions (List[str]): List of required permissions.

    Returns:
        Callable: Dependency function for permission verification.

    Raises:
        ValueError: If the permissions list is empty.
    """
    if not permissions:
        raise ValueError("Permissions list cannot be empty.")

    async def permission_dependency(current_user=Depends(get_current_active_user)):
        for permission in permissions:
            if not await rbac_system.verify_permission(str(current_user.id), permission):
                logger.warning(f"User {current_user.id} lacks required permission: {permission}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {permission}"
                )
        logger.info(f"User {current_user.id} has all required permissions.")
        return current_user

    return permission_dependency


def require_role(allowed_roles: List[str]):
    """
    Dependency factory for requiring specific roles.

    Args:
        allowed_roles (List[str]): List of allowed roles.

    Returns:
        Callable: Dependency function for role verification.

    Raises:
        ValueError: If the allowed_roles list is empty.
    """
    if not allowed_roles:
        raise ValueError("Allowed roles list cannot be empty.")

    async def role_dependency(current_user=Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            logger.warning(f"User {current_user.id} has unauthorized role: {current_user.role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not authorized"
            )
        logger.info(f"User {current_user.id} has an authorized role: {current_user.role}")
        return current_user

    return role_dependency