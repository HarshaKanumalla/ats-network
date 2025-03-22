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
    # Configuration
    "Settings",
    "get_settings",
    "initialize_logging",
    
    # Security and Authentication
    "security_manager",
    "auth_manager",
    "token_service",
    "rbac_system",
    
    # Database Management
    "db_manager",
    "db_validator",
    "query_optimizer",
    
    # Constants and Enums
    "UserRole",
    "UserStatus",
    "TestType",
    "TestStatus",
    "CenterStatus",
    "DocumentType",
    "NotificationType",
    
    # Exceptions
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
    
    try:
        # First initialize database since other services depend on it
        db_manager.connect()
        
        # Initialize security before auth since auth depends on security
        security_manager.initialize()
        
        # Initialize auth after security is ready
        auth_manager.initialize()
        
        # Initialize RBAC last since it depends on auth being ready
        rbac_system.initialize()
        
        logger.info("Core services initialized successfully")
        return settings
        
    except Exception as e:
        logger.error(f"Failed to initialize core services: {str(e)}")
        raise ConfigurationError("Core service initialization failed")

def initialize_test_services():
    """Initialize test-related services with proper dependency management."""
    try:
        # Create base services first
        test_service = TestService(test_monitor=None, results_service=None)
        
        # Create monitor service with reference to test service
        test_monitor = TestMonitor(
            test_service=test_service,
            results_service=None
        )
        
        # Create results service with both dependencies
        results_service = TestResultsService(
            test_service=test_service,
            test_monitor=test_monitor
        )
        
        # Update the circular references
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
        # Check database connectivity
        await db_manager.check_health()
        
        # Verify security service
        await security_manager.verify_configuration()
        
        # Check authentication service
        await auth_manager.verify_status()
        
        # Validate RBAC configuration
        await rbac_system.verify_permissions()
        
        logger.info("Core service health checks passed")
        
    except Exception as e:
        logger.error(f"Core service health check failed: {str(e)}")
        raise ConfigurationError("Core services failed health check")

async def shutdown_core():
    """Properly shut down core services and clean up resources."""
    try:
        # Shut down in reverse order of initialization
        await rbac_system.cleanup()
        await auth_manager.cleanup()
        await security_manager.cleanup()
        await db_manager.cleanup()
        
        logger.info("Core services shut down successfully")
        
    except Exception as e:
        logger.error(f"Error during core service shutdown: {str(e)}")
        raise ConfigurationError("Failed to shut down core services properly")

