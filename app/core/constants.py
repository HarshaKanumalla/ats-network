# backend/app/core/constants.py

from enum import Enum

# User Roles
class UserRole(str, Enum):
    """User role definitions for the ATS system."""
    TRANSPORT_COMMISSIONER = "transport_commissioner"
    ADDITIONAL_COMMISSIONER = "additional_commissioner"
    RTO_OFFICER = "rto_officer"
    ATS_OWNER = "ats_owner"
    ATS_ADMIN = "ats_admin"
    ATS_TESTING = "ats_testing"

# User Status
class UserStatus(str, Enum):
    """User account status definitions."""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"

# Test Types
class TestType(str, Enum):
    """Vehicle test type definitions."""
    SPEED = "speed_test"
    BRAKE = "brake_test"
    NOISE = "noise_test"
    HEADLIGHT = "headlight_test"
    AXLE = "axle_test"

# Test Status
class TestStatus(str, Enum):
    """Test session status definitions."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# Center Status
class CenterStatus(str, Enum):
    """ATS center status definitions."""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"

# Document Types
class DocumentType(str, Enum):
    """Document type definitions."""
    REGISTRATION = "registration"
    LICENSE = "license"
    INSURANCE = "insurance"
    TEST_REPORT = "test_report"
    CALIBRATION = "calibration"
    CENTER_APPROVAL = "center_approval"

# Notification Types
class NotificationType(str, Enum):
    """Notification type definitions."""
    TEST_COMPLETE = "test_complete"
    APPROVAL_REQUIRED = "approval_required"
    DOCUMENT_EXPIRED = "document_expired"
    MAINTENANCE_DUE = "maintenance_due"
    SYSTEM_ALERT = "system_alert"

# Database Collection Names
COLLECTION_USERS = "users"
COLLECTION_CENTERS = "centers"
COLLECTION_TESTS = "test_sessions"
COLLECTION_VEHICLES = "vehicles"
COLLECTION_NOTIFICATIONS = "notifications"
COLLECTION_AUDIT_LOGS = "audit_logs"

# Cache Keys Prefixes
CACHE_PREFIX_USER = "user:"
CACHE_PREFIX_CENTER = "center:"
CACHE_PREFIX_VEHICLE = "vehicle:"
CACHE_PREFIX_TEST = "test:"

# File Storage Paths
STORAGE_PATH_DOCUMENTS = "documents/"
STORAGE_PATH_REPORTS = "reports/"
STORAGE_PATH_IMAGES = "images/"
STORAGE_PATH_TEMP = "temp/"

# Validation Constants
MAX_FILE_SIZE_MB = 10
MAX_IMAGE_SIZE_MB = 5
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png"]
ALLOWED_DOCUMENT_TYPES = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]
PASSWORD_MIN_LENGTH = 8
USERNAME_MIN_LENGTH = 3

# Time Constants
TOKEN_EXPIRY_MINUTES = 30
REFRESH_TOKEN_EXPIRY_DAYS = 7
PASSWORD_RESET_EXPIRY_HOURS = 24
VERIFICATION_CODE_EXPIRY_MINUTES = 15

# Rate Limiting
MAX_LOGIN_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900
DEFAULT_RATE_LIMIT = 100
AUTH_RATE_LIMIT = 20

# Geographic Constants
MAX_SEARCH_RADIUS_KM = 100
INDIA_BOUNDS = {
    "north": 37.5,
    "south": 6.5,
    "east": 97.5,
    "west": 68.0
}

# Test Parameters
MAX_TEST_DURATION_MINUTES = 120
MIN_BRAKE_FORCE = 50
MAX_NOISE_LEVEL = 90
MAX_SPEED_KMH = 120