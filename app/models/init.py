"""Model initialization and organization for the ATS Network System.

This module serves as the central point for importing all model definitions
and provides version control and metadata for the models package.
"""

import sys
import logging
import pkg_resources
from datetime import datetime
from typing import Dict, List, Set, Type
from enum import Enum, auto
from pathlib import Path

# Initialize logging
logger = logging.getLogger(__name__)

# Version and metadata
__version__: str = "1.0.0"
__author__: str = "ATS Network Team"
MINIMUM_PYTHON_VERSION: tuple = (3, 9)
COMPATIBLE_DATABASE_VERSIONS: List[str] = ["4.4", "5.0", "6.0"]
MODULE_INITIALIZED: datetime = datetime.utcnow()

# Package requirements
REQUIRED_PACKAGES: Dict[str, str] = {
    "pydantic": ">=2.0.0",
    "pymongo": ">=4.0.0",
    "bson": "*",
}

# Circular import prevention
_imported: Set[str] = set()

class ModelCategory(Enum):
    """Categories for model organization."""
    COMMON = auto()
    LOCATION = auto()
    USER = auto()
    CENTER = auto()
    TEST = auto()
    VEHICLE = auto()
    NOTIFICATION = auto()
    AUDIT = auto()
    REPORT = auto()
    MONITORING = auto()

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

# Model Registry
MODEL_REGISTRY: Dict[ModelCategory, List[Type]] = {
    ModelCategory.COMMON: [
        BaseModel, PyObjectId, TimestampedModel, DocumentModel,
        StatusModel, MetadataModel, AuditedModel
    ],
    ModelCategory.LOCATION: [
        Coordinates, Address, Location, LocationCreate,
        LocationUpdate, LocationResponse, GeoSearchQuery
    ],
    ModelCategory.USER: [
        User, UserCreate, UserUpdate, UserInDB, UserResponse,
        UserSession, UserPermission, ActivityLog, SecurityProfile,
        RoleAssignment, UserProfile
    ],
    ModelCategory.CENTER: [
        ATSCenter, CenterCreate, CenterUpdate, CenterResponse,
        CenterEquipment, CenterDocument, CenterStatistics
    ],
    ModelCategory.TEST: [
        TestSession, TestResult, TestResponse, TestStep,
        TestMeasurement, QualityCheck, TestVerification,
        TestProcedure, TestMonitoring, TestCalibration
    ],
    ModelCategory.VEHICLE: [
        Vehicle, VehicleCreate, VehicleUpdate, VehicleResponse,
        VehicleCategory, DocumentVerification, TestHistoryEntry,
        OwnershipRecord
    ],
    ModelCategory.NOTIFICATION: [
        Notification, NotificationTemplate, DeliveryAttempt,
        NotificationPreferences, NotificationGroup, NotificationBatch,
        EmailNotification, SMSNotification, PushNotification,
        NotificationStatus
    ],
    ModelCategory.AUDIT: [
        AuditEvent, AuditCategory, AuditAction, EntityType,
        DataChange, SecurityContext, ComplianceMetadata,
        AuditLogQuery, AuditTrail, ComplianceReport,
        AuditArchive, AuditConfiguration
    ],
    ModelCategory.REPORT: [
        Report, ReportType, ReportFormat, ReportSection,
        ReportTemplate, ReportSchedule, ReportGeneration,
        ReportDistribution, ReportAccess
    ],
    ModelCategory.MONITORING: [
        SystemHealth, PerformanceMetrics, ResourceUtilization,
        AlertConfiguration, MonitoringThreshold, ServiceStatus
    ]
}

def prevent_circular_imports(module_name: str) -> None:
    """Prevent circular imports between models."""
    if module_name in _imported:
        raise ImportError(f"Circular import detected: {module_name}")
    _imported.add(module_name)

def setup_logging() -> None:
    """Configure package logging."""
    log_file = Path(__file__).parent / "models.log"
    handler = logging.FileHandler(log_file)
    handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info(f"Models package initialized. Version: {__version__}")

def check_dependencies() -> None:
    """Verify required package versions."""
    missing = []
    for package, version in REQUIRED_PACKAGES.items():
        try:
            pkg_resources.require(f"{package}{version}")
        except (pkg_resources.VersionConflict, pkg_resources.DistributionNotFound) as e:
            missing.append(f"{package}: {str(e)}")
    if missing:
        raise ImportError("Missing dependencies:\n" + "\n".join(missing))

def check_compatibility() -> bool:
    """Check system compatibility."""
    if sys.version_info[:2] < MINIMUM_PYTHON_VERSION:
        raise RuntimeError(f"Python {'.'.join(map(str, MINIMUM_PYTHON_VERSION))} or higher required")
    return True

def validate_models() -> None:
    """Validate all model definitions."""
    validation_errors = []
    for category, models in MODEL_REGISTRY.items():
        for model in models:
            try:
                if hasattr(model, 'model_json_schema'):
                    model.model_json_schema()
                    logger.debug(f"Validated model: {model.__name__}")
            except Exception as e:
                validation_errors.append(f"{model.__name__}: {str(e)}")
    if validation_errors:
        raise ImportError("Model validation failed:\n" + "\n".join(validation_errors))

def generate_models_documentation() -> str:
    """Generate documentation for all models."""
    docs = ["# ATS Network System Models\n"]
    for category, models in MODEL_REGISTRY.items():
        docs.append(f"\n## {category.name} Models\n")
        for model in models:
            docs.append(f"### {model.__name__}\n")
            if model.__doc__:
                docs.append(f"{model.__doc__.strip()}\n")
            if hasattr(model, 'model_json_schema'):
                docs.append("#### Schema\n```json\n")
                docs.append(str(model.model_json_schema()))
                docs.append("\n```\n")
    return "\n".join(docs)

# Initialize module
prevent_circular_imports(__name__)
setup_logging()
check_dependencies()
check_compatibility()
validate_models()

# Export all models
__all__ = [
    model.__name__
    for models in MODEL_REGISTRY.values()
    for model in models
]

# Generate documentation if run directly
if __name__ == "__main__":
    docs = generate_models_documentation()
    docs_path = Path(__file__).parent / "models_documentation.md"
    docs_path.write_text(docs)
    logger.info(f"Documentation generated at: {docs_path}")