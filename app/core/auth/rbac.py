# backend/app/core/auth/rbac.py

from typing import Dict, Any, List, Set, Optional
import logging
from datetime import datetime
from fastapi import HTTPException, status
from bson import ObjectId

from ...core.exceptions import AuthorizationError
from ...services.audit.service import audit_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RoleBasedAccessControl:
    """Manages role-based access control and permissions."""

    def __init__(self):
        """Initialize RBAC with role hierarchy and permissions."""
        self.security_service = None
        self._initialized = False

        # Role hierarchy and permissions
        self.role_hierarchy = {
            "transport_commissioner": [
                "additional_commissioner",
                "rto_officer",
                "ats_owner",
                "ats_admin",
                "ats_testing"
            ],
            "additional_commissioner": [
                "rto_officer",
                "ats_owner",
                "ats_admin",
                "ats_testing"
            ],
            "rto_officer": [
                "ats_admin",
                "ats_testing"
            ],
            "ats_owner": [
                "ats_admin",
                "ats_testing"
            ],
            "ats_admin": [
                "ats_testing"
            ]
        }

        self.role_permissions = {
            "transport_commissioner": {
                "manage_system_settings",
                "view_audit_logs",
                "manage_system_maintenance",
                "manage_users",
                "manage_roles",
                "view_all_users",
                "manage_centers",
                "approve_centers",
                "view_all_centers",
                "view_system_analytics",
                "generate_system_reports",
                "view_all_statistics"
            },
            "additional_commissioner": {
                "view_all_centers",
                "approve_centers",
                "approve_tests",
                "view_test_reports",
                "view_regional_analytics",
                "view_center_statistics"
            },
            "rto_officer": {
                "manage_vehicles",
                "view_vehicle_history",
                "approve_tests",
                "view_test_reports",
                "view_assigned_centers"
            },
            "ats_owner": {
                "manage_own_center",
                "view_center_reports",
                "manage_center_staff",
                "manage_equipment",
                "view_center_analytics"
            },
            "ats_admin": {
                "manage_tests",
                "schedule_tests",
                "view_test_history",
                "manage_equipment_status",
                "view_equipment_reports"
            },
            "ats_testing": {
                "conduct_tests",
                "upload_test_data",
                "view_test_results"
            }
        }

        logger.info("RBAC system initialized with role hierarchy and permissions")

    async def initialize(self):
        """Initialize RBAC system with required dependencies."""
        if not self._initialized:
            from ..security import security_manager
            self.security_service = security_manager
            self._initialized = True
            logger.info("RBAC system dependencies initialized")

    async def verify_permission(
        self,
        user_id: str,
        required_permission: str,
        resource_id: Optional[str] = None
    ) -> bool:
        """
        Verify if a user has the required permission for a resource.

        Args:
            user_id (str): User identifier.
            required_permission (str): Permission to check.
            resource_id (Optional[str]): Optional resource identifier.

        Returns:
            bool: True if the user has permission, False otherwise.

        Raises:
            AuthorizationError: If verification fails.
        """
        try:
            if not ObjectId.is_valid(user_id):
                raise ValueError("Invalid user ID format")

            db = await get_database()
            user = await db.users.find_one({"_id": ObjectId(user_id)})

            if not user:
                raise AuthorizationError("User not found")

            # Get all permissions for user's role
            user_permissions = await self.get_role_permissions(user["role"])

            # Check for required permission
            if required_permission not in user_permissions:
                logger.warning(f"User {user_id} lacks permission: {required_permission}")
                return False

            # Handle resource-specific permissions
            if resource_id:
                if not await self._verify_resource_access(
                    user=user,
                    resource_id=resource_id,
                    permission=required_permission
                ):
                    logger.warning(f"User {user_id} lacks resource-specific permission: {required_permission}")
                    return False

            logger.info(f"Permission '{required_permission}' verified successfully for user ID: {user_id}")
            return True

        except AuthorizationError:
            raise
        except Exception as e:
            logger.error(f"Permission verification error for user ID {user_id}: {str(e)}")
            raise AuthorizationError("Failed to verify permission")

    async def get_role_permissions(self, role: str) -> Set[str]:
        """
        Get all permissions for a role, including inherited permissions.

        Args:
            role (str): Role identifier.

        Returns:
            Set[str]: Set of all permissions for the role.
        """
        permissions = set(self.role_permissions.get(role, set()))

        # Add inherited permissions
        for inherited_role in self.role_hierarchy.get(role, []):
            permissions.update(self.role_permissions.get(inherited_role, set()))

        return permissions

    async def assign_role(
        self,
        user_id: str,
        new_role: str,
        assigned_by: str
    ) -> Dict[str, Any]:
        """
        Assign a new role to a user with proper validation.

        Args:
            user_id (str): User identifier.
            new_role (str): Role to assign.
            assigned_by (str): Administrator making the change.

        Returns:
            Dict[str, Any]: Updated user information.

        Raises:
            AuthorizationError: If role assignment fails.
        """
        try:
            if not ObjectId.is_valid(user_id) or not ObjectId.is_valid(assigned_by):
                raise ValueError("Invalid user ID format")

            db = await get_database()

            # Validate role exists
            if new_role not in self.role_hierarchy and new_role not in self.role_permissions:
                raise AuthorizationError("Invalid role")

            # Validate assigner's permissions
            assigner = await db.users.find_one({"_id": ObjectId(assigned_by)})
            if not assigner:
                raise AuthorizationError("Assigning user not found")

            if not await self.check_role_hierarchy(assigner["role"], new_role):
                raise AuthorizationError("Insufficient permissions to assign this role")

            # Update user role
            result = await db.users.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "role": new_role,
                        "roleUpdatedAt": datetime.utcnow(),
                        "roleUpdatedBy": ObjectId(assigned_by)
                    }
                },
                return_document=True
            )

            if not result:
                raise AuthorizationError("User not found")

            # Log role change
            await audit_service.log_role_change(
                user_id=user_id,
                old_role=result.get("role"),
                new_role=new_role,
                changed_by=assigned_by
            )

            logger.info(f"Role '{new_role}' assigned to user ID {user_id} by admin ID {assigned_by}")
            return result

        except AuthorizationError:
            raise
        except Exception as e:
            logger.error(f"Role assignment error for user ID {user_id}: {str(e)}")
            raise AuthorizationError("Failed to assign role")

    async def check_role_hierarchy(
        self,
        admin_role: str,
        target_role: str
    ) -> bool:
        """
        Check if an admin role can manage a target role.

        Args:
            admin_role (str): Role of the administrator.
            target_role (str): Role being managed.

        Returns:
            bool: True if the admin can manage the target role, False otherwise.
        """
        if admin_role == target_role:
            return False

        return target_role in self.role_hierarchy.get(admin_role, [])

    async def filter_data_by_role(
        self,
        user_id: str,
        data_type: str,
        data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter data based on the user's role and permissions.

        Args:
            user_id (str): User identifier.
            data_type (str): Type of data being filtered.
            data (List[Dict[str, Any]]): Data to filter.

        Returns:
            List[Dict[str, Any]]: Filtered data list.

        Raises:
            AuthorizationError: If filtering fails.
        """
        try:
            db = await get_database()
            user = await db.users.find_one({"_id": ObjectId(user_id)})

            if not user:
                raise AuthorizationError("User not found")

            # Handle different data types
            if data_type == "centers":
                return await self._filter_center_data(user, data)
            elif data_type == "vehicles":
                return await self._filter_vehicle_data(user, data)
            elif data_type == "tests":
                return await self._filter_test_data(user, data)
            else:
                logger.warning(f"Unsupported data type '{data_type}' for filtering")
                return []

        except Exception as e:
            logger.error(f"Data filtering error: {str(e)}")
            raise AuthorizationError("Failed to filter data")

    async def _verify_resource_access(
        self,
        user: Dict[str, Any],
        resource_id: str,
        permission: str
    ) -> bool:
        """
        Verify a user's access to a specific resource.

        Args:
            user (Dict[str, Any]): User information.
            resource_id (str): Resource identifier.
            permission (str): Required permission.

        Returns:
            bool: True if the user has access, False otherwise.
        """
        try:
            db = await get_database()

            # Handle center-specific permissions
            if permission.startswith("center_"):
                center = await db.centers.find_one({"_id": ObjectId(resource_id)})
                if not center:
                    logger.warning(f"Center {resource_id} not found")
                    return False

                if user["role"] == "ats_owner":
                    return str(center["ownerId"]) == str(user["_id"])
                elif user["role"] == "rto_officer":
                    return center["district"] in user.get("jurisdiction", [])

            # Handle test-specific permissions
            elif permission.startswith("test_"):
                test = await db.tests.find_one({"_id": ObjectId(resource_id)})
                if not test:
                    logger.warning(f"Test {resource_id} not found")
                    return False

                if user["role"] in ["ats_admin", "ats_testing"]:
                    return str(test["centerId"]) == str(user.get("centerId"))

            # Handle vehicle-specific permissions
            elif permission.startswith("vehicle_"):
                vehicle = await db.vehicles.find_one({"_id": ObjectId(resource_id)})
                if not vehicle:
                    logger.warning(f"Vehicle {resource_id} not found")
                    return False

                if user["role"] == "rto_officer":
                    return vehicle["registrationDistrict"] in user.get("jurisdiction", [])

            return True

        except Exception as e:
            logger.error(f"Resource access verification error: {str(e)}")
            return False

    async def _filter_center_data(
        self,
        user: Dict[str, Any],
        data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter center data based on the user's role."""
        if user["role"] in ["transport_commissioner", "additional_commissioner"]:
            return data
        elif user["role"] == "rto_officer":
            return [
                center for center in data
                if center["district"] in user.get("jurisdiction", [])
            ]
        elif user["role"] in ["ats_owner", "ats_admin", "ats_testing"]:
            return [
                center for center in data
                if str(center["_id"]) == str(user.get("centerId"))
            ]
        return []


# Initialize RBAC system
rbac_system = RoleBasedAccessControl()