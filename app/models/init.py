"""Model initialization and organization for the ATS Network System.

This module serves as the central point for importing all model definitions
and provides version control and metadata for the models package.
"""

__version__ = "1.0.0"
__author__ = "ATS Network Team"

from datetime import datetime

# Common Models
from .common import (
    BaseModel,
    PyObjectId,
    TimestampedModel,
    DocumentModel,
    StatusModel,
    MetadataModel,
    AuditedModel
)

# Location Models
from .location import (
    Coordinates,
    Address,
    Location,
    LocationCreate,
    LocationUpdate,
    LocationResponse,
    GeoSearchQuery
)

# User Models
from .user import (
    User,
    UserCreate,
    UserUpdate,
    UserInDB,
    UserResponse,
    UserSession,
    UserPermission,
    ActivityLog,
    SecurityProfile,
    RoleAssignment,
    UserProfile
)

# Center Models
from .center import (
    ATSCenter,
    CenterCreate,
    CenterUpdate,
    CenterResponse,
    CenterEquipment,
    CenterDocument,
    CenterStatistics
)

# Test Models
from .test import (
    TestSession,
    TestResult,
    TestResponse,
    TestStep,
    TestMeasurement,
    QualityCheck,
    TestVerification,
    TestProcedure,
    TestMonitoring,
    TestCalibration
)

# Vehicle Models
from .vehicle import (
    Vehicle,
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
    VehicleCategory,
    DocumentVerification,
    TestHistoryEntry,
    OwnershipRecord
)

# Notification Models
from .notification import (
    Notification,
    NotificationTemplate,
    DeliveryAttempt,
    NotificationPreferences,
    NotificationGroup,
    NotificationBatch,
    EmailNotification,
    SMSNotification,
    PushNotification,
    NotificationStatus
)

# Audit Models
from .audit import (
    AuditEvent,
    AuditCategory,
    AuditAction,
    EntityType,
    DataChange,
    SecurityContext,
    ComplianceMetadata,
    AuditLogQuery,
    AuditTrail,
    ComplianceReport,
    AuditArchive,
    AuditConfiguration
)

# Report Models
from .report import (
    Report,
    ReportType,
    ReportFormat,
    ReportSection,
    ReportTemplate,
    ReportSchedule,
    ReportGeneration,
    ReportDistribution,
    ReportAccess
)

# Monitoring Models
from .monitoring import (
    SystemHealth,
    PerformanceMetrics,
    ResourceUtilization,
    AlertConfiguration,
    MonitoringThreshold,
    ServiceStatus
)

__all__ = [
    # Common Models
    "BaseModel",
    "PyObjectId",
    "TimestampedModel",
    "DocumentModel",
    "StatusModel",
    "MetadataModel",
    "AuditedModel",
    
    # Location Models
    "Coordinates",
    "Address",
    "Location",
    "LocationCreate",
    "LocationUpdate",
    "LocationResponse",
    "GeoSearchQuery",
    
    # User Models
    "User",
    "UserCreate",
    "UserUpdate",
    "UserInDB",
    "UserResponse",
    "UserSession",
    "UserPermission",
    "ActivityLog",
    "SecurityProfile",
    "RoleAssignment",
    "UserProfile",
    
    # Center Models
    "ATSCenter",
    "CenterCreate",
    "CenterUpdate",
    "CenterResponse",
    "CenterEquipment",
    "CenterDocument",
    "CenterStatistics",
    
    # Test Models
    "TestSession",
    "TestResult",
    "TestResponse",
    "TestStep",
    "TestMeasurement",
    "QualityCheck",
    "TestVerification",
    "TestProcedure",
    "TestMonitoring",
    "TestCalibration",
    
    # Vehicle Models
    "Vehicle",
    "VehicleCreate",
    "VehicleUpdate",
    "VehicleResponse",
    "VehicleCategory",
    "DocumentVerification",
    "TestHistoryEntry",
    "OwnershipRecord",
    
    # Notification Models
    "Notification",
    "NotificationTemplate",
    "DeliveryAttempt",
    "NotificationPreferences",
    "NotificationGroup",
    "NotificationBatch",
    "EmailNotification",
    "SMSNotification",
    "PushNotification",
    "NotificationStatus",
    
    # Audit Models
    "AuditEvent",
    "AuditCategory",
    "AuditAction",
    "EntityType",
    "DataChange",
    "SecurityContext",
    "ComplianceMetadata",
    "AuditLogQuery",
    "AuditTrail",
    "ComplianceReport",
    "AuditArchive",
    "AuditConfiguration",
    
    # Report Models
    "Report",
    "ReportType",
    "ReportFormat",
    "ReportSection",
    "ReportTemplate",
    "ReportSchedule",
    "ReportGeneration",
    "ReportDistribution",
    "ReportAccess",
    
    # Monitoring Models
    "SystemHealth",
    "PerformanceMetrics",
    "ResourceUtilization",
    "AlertConfiguration",
    "MonitoringThreshold",
    "ServiceStatus"
]

# Module initialization timestamp
MODULE_INITIALIZED = datetime.utcnow()