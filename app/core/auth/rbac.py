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
                # System Administration
                "manage_system_settings",
                "view_audit_logs",
                "manage_system_maintenance",
                
                # User Management
                "manage_users",
                "manage_roles",
                "view_all_users",
                
                # Center Management
                "manage_centers",
                "approve_centers",
                "view_all_centers",
                
                # Analytics & Reports
                "view_system_analytics",
                "generate_system_reports",
                "view_all_statistics"
            },
            "additional_commissioner": {
                # Center Management
                "view_all_centers",
                "approve_centers",
                
                # Test Management
                "approve_tests",
                "view_test_reports",
                
                # Analytics & Reports
                "view_regional_analytics",
                "view_center_statistics"
            },
            "rto_officer": {
                # Vehicle Management
                "manage_vehicles",
                "view_vehicle_history",
                
                # Test Management
                "approve_tests",
                "view_test_reports",
                
                # Center Management
                "view_assigned_centers"
            },
            "ats_owner": {
                # Center Management
                "manage_own_center",
                "view_center_reports",
                
                # Staff Management
                "manage_center_staff",
                
                # Equipment Management
                "manage_equipment",
                
                # Analytics
                "view_center_analytics"
            },
            "ats_admin": {
                # Test Management
                "manage_tests",
                "schedule_tests",
                "view_test_history",
                
                # Equipment Management
                "manage_equipment_status",
                "view_equipment_reports"
            },
            "ats_testing": {
                # Test Operations
                "conduct_tests",
                "upload_test_data",
                "view_test_results"
            }
        }
        
        logger.info("RBAC system initialized with role hierarchy")

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
        """Verify if user has required permission for a resource.
        
        Args:
            user_id: User identifier
            required_permission: Permission to check
            resource_id: Optional resource identifier
            
        Returns:
            True if user has permission, False otherwise
            
        Raises:
            AuthorizationError: If verification fails
        """
        try:
            db = await get_database()
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                raise AuthorizationError("User not found")

            # Get all permissions for user's role
            user_permissions = await self.get_role_permissions(user["role"])

            # Check for required permission
            if required_permission not in user_permissions:
                return False

            # Handle resource-specific permissions
            if resource_id:
                if not await self._verify_resource_access(
                    user=user,
                    resource_id=resource_id,
                    permission=required_permission
                ):
                    return False

            return True

        except AuthorizationError:
            raise
        except Exception as e:
            logger.error(f"Permission verification error: {str(e)}")
            return False

    async def get_role_permissions(self, role: str) -> Set[str]:
        """Get all permissions for a role including inherited permissions.
        
        Args:
            role: Role identifier
            
        Returns:
            Set of all permissions for the role
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
        """Assign new role to user with proper validation.
        
        Args:
            user_id: User identifier
            new_role: Role to assign
            assigned_by: Administrator making the change
            
        Returns:
            Updated user information
            
        Raises:
            AuthorizationError: If role assignment fails
        """
        try:
            db = await get_database()
            
            # Validate role exists
            if new_role not in self.role_hierarchy and new_role not in self.role_permissions:
                raise AuthorizationError("Invalid role")

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

            return result

        except AuthorizationError:
            raise
        except Exception as e:
            logger.error(f"Role assignment error: {str(e)}")
            raise AuthorizationError("Failed to assign role")

    async def check_role_hierarchy(
        self,
        admin_role: str,
        target_role: str
    ) -> bool:
        """Check if admin role can manage target role.
        
        Args:
            admin_role: Role of administrator
            target_role: Role being managed
            
        Returns:
            True if admin can manage target role, False otherwise
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
        """Filter data based on user's role and permissions.
        
        Args:
            user_id: User identifier
            data_type: Type of data being filtered
            data: Data to filter
            
        Returns:
            Filtered data list
            
        Raises:
            AuthorizationError: If filtering fails
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
        """Verify user's access to specific resource.
        
        Args:
            user: User information
            resource_id: Resource identifier
            permission: Required permission
            
        Returns:
            True if user has access, False otherwise
        """
        try:
            db = await get_database()
            
            # Handle center-specific permissions
            if permission.startswith("center_"):
                center = await db.centers.find_one({"_id": ObjectId(resource_id)})
                if not center:
                    return False
                    
                if user["role"] == "ats_owner":
                    return str(center["ownerId"]) == str(user["_id"])
                elif user["role"] == "rto_officer":
                    return center["district"] in user.get("jurisdiction", [])
            
            # Handle test-specific permissions
            elif permission.startswith("test_"):
                test = await db.tests.find_one({"_id": ObjectId(resource_id)})
                if not test:
                    return False
                    
                if user["role"] in ["ats_admin", "ats_testing"]:
                    return str(test["centerId"]) == str(user.get("centerId"))
            
            # Handle vehicle-specific permissions
            elif permission.startswith("vehicle_"):
                vehicle = await db.vehicles.find_one({"_id": ObjectId(resource_id)})
                if not vehicle:
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
        """Filter center data based on user's role."""
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


