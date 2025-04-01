from .config import Settings, get_settings, initialize_logging
from .exceptions import (
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    DatabaseError,
    TestError,
    CenterError,
    VehicleError,
    FileOperationError,
    EmailError,
    ReportError,
    ConfigurationError,
    ExternalServiceError,
    RateLimitError
)
from .constants import (
    UserRole,
    UserStatus,
    TestType,
    TestStatus,
    CenterStatus,
    DocumentType,
    NotificationType
)
from .security import security_manager
from .auth.manager import auth_manager
from .auth.token import token_service
from .auth.rbac import rbac_system
from .database.manager import db_manager
from .database.validator import db_validator
from .database.query_optimizer import query_optimizer

import logging
logger = logging.getLogger(__name__)

__version__ = "1.0.0"

__all__ = [
    "Settings",
    "get_settings",
    "initialize_logging",
    "security_manager",
    "auth_manager",
    "token_service",
    "rbac_system",
    "db_manager",
    "db_validator",
    "query_optimizer",
    "UserRole",
    "UserStatus",
    "TestType",
    "TestStatus",
    "CenterStatus",
    "DocumentType",
    "NotificationType",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "DatabaseError",
    "TestError",
    "CenterError",
    "VehicleError",
    "FileOperationError",
    "EmailError",
    "ReportError",
    "ConfigurationError",
    "ExternalServiceError",
    "RateLimitError"
]

def initialize_core():
    """Initialize core services and configurations."""
    settings = get_settings()
    initialize_logging()
    logger.info(f"Initializing core services for ATS Network v{__version__}")
    
    try:
        db_manager.connect()
        security_manager.initialize()
        auth_manager.initialize()
        rbac_system.initialize()
        
        logger.info("Core services initialized successfully")
        return settings
    except Exception as e:
        logger.error(f"Failed to initialize core services: {str(e)}")
        raise ConfigurationError("Core service initialization failed")

def initialize_test_services():
    """Initialize test-related services with proper dependency management."""
    try:
        test_service = TestService(test_monitor=None, results_service=None)
        test_monitor = TestMonitor(test_service=test_service, results_service=None)
        results_service = TestResultsService(test_service=test_service, test_monitor=test_monitor)
        
        test_service.test_monitor = test_monitor
        test_service.test_results = results_service
        test_monitor.results_service = results_service
        
        logger.info("Test services initialized successfully")
        return test_service, test_monitor, results_service
    except Exception as e:
        logger.error(f"Failed to initialize test services: {str(e)}")
        raise ConfigurationError("Test service initialization failed")

async def verify_core_services():
    """Verify all core services are functioning properly."""
    try:
        await db_manager.check_health()
        logger.info("Database manager health check passed")
        
        await security_manager.verify_configuration()
        logger.info("Security manager health check passed")
        
        await auth_manager.verify_status()
        logger.info("Authentication manager health check passed")
        
        await rbac_system.verify_permissions()
        logger.info("RBAC system health check passed")
        
        logger.info("Core service health checks passed")
    except Exception as e:
        logger.error(f"Core service health check failed: {str(e)}")
        raise ConfigurationError("Core services failed health check")

async def shutdown_core():
    """Properly shut down core services and clean up resources."""
    try:
        await rbac_system.cleanup()
        await auth_manager.cleanup()
        await security_manager.cleanup()
        await db_manager.cleanup()
        
        logger.info("Core services shut down successfully")
    except Exception as e:
        logger.error(f"Error during core service shutdown: {str(e)}")
        raise ConfigurationError("Failed to shut down core services properly")