# backend/app/docs/exception_mapping.md

# Exception Usage Guide

## Service-Level Exceptions

### Authentication Service
- AuthenticationError: Invalid credentials, token expiration
- AuthorizationError: Insufficient permissions

### Test Service
- TestError: Invalid test parameters, test session errors
- ValidationError: Test data validation failures

### Center Service
- CenterError: Center registration, equipment management
- ValidationError: Center data validation

### Vehicle Service
- VehicleError: Vehicle registration, document management
- ValidationError: Vehicle data validation

## System-Level Exceptions

### Database Operations
- DatabaseError: Connection issues, query failures
- ValidationError: Schema validation failures

### File Operations
- FileOperationError: Upload/download failures
- StorageError: S3 operation failures

### Configuration
- ConfigurationError: Invalid environment setup
- ValidationError: Configuration validation failures