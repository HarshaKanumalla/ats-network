# ATS Networking Software - Comprehensive Architecture Document

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [Architectural Design](#architectural-design)
4. [Technology Stack](#technology-stack)
5. [Security Architecture](#security-architecture)
6. [Data Management Strategy](#data-management-strategy)
7. [User Management and Authentication](#user-management-and-authentication)
8. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
9. [Module Design](#module-design)
10. [Integration Architecture](#integration-architecture)
11. [Performance Optimization](#performance-optimization)
12. [Audit and Compliance](#audit-and-compliance)
13. [Deployment Strategy](#deployment-strategy)
14. [Monitoring and Logging](#monitoring-and-logging)
15. [Disaster Recovery and Business Continuity](#disaster-recovery-and-business-continuity)
16. [Scalability Considerations](#scalability-considerations)
17. [Development Methodology](#development-methodology)
18. [Testing Strategy](#testing-strategy)
19. [Conclusion](#conclusion)

## Executive Summary

The Automated Testing Station (ATS) Networking Software is a sophisticated system designed to manage the vehicle fitness test process for yellow number-plated vehicles in India. The system bridges the gap between government requirements, vehicle owners, and testing centers, providing a seamless workflow from appointment scheduling to certification issuance.

This document outlines a comprehensive architectural approach for developing the ATS Networking Software using Python (backend) and React.js (frontend). The architecture focuses on security, scalability, and compliance with government regulations while ensuring an intuitive user experience for all stakeholders involved in the vehicle testing process.

## System Overview

The ATS Networking Software facilitates the management of vehicle fitness tests across multiple testing centers. It connects to the Parivaahan portal (a government portal) to receive vehicle test appointments and sends back test results and certification information. The system supports various roles including administrators, government officials, testing center personnel, and owners.

### Key Functions
- User registration and authentication with role-based access control
- ATS center registration, verification, and management
- Vehicle test scheduling and management
- Real-time collection and processing of test data from testing equipment
- Automated document generation (Form 69, receipts)
- Submission of test results to government portal
- Comprehensive reporting and analytics
- Data storage and management using MongoDB and Amazon S3

## Architectural Design

The ATS Networking Software will be built on a modern, microservices-based architecture that separates concerns, enhances security, and enables scalability.

### High-Level Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────────────┐
│ Client (Browser)│◄────┤ CDN/WAF      │◄────┤ Load Balancer         │
└────────┬────────┘     └──────────────┘     └───────────┬───────────┘
         │                                               │
         │                                               │
         ▼                                               ▼
┌─────────────────┐                          ┌───────────────────────┐
│ React Frontend  │                          │ API Gateway           │
└────────┬────────┘                          └───────────┬───────────┘
         │                                               │
         │                                               │
         ▼                                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Service Layer (Microservices)                    │
├────────────────┬──────────────┬─────────────────┬──────────────────┤
│ Auth Service   │ ATS Service  │ Vehicle Service │ Testing Service  │
├────────────────┼──────────────┼─────────────────┼──────────────────┤
│ Admin Service  │ User Service │ Report Service  │ Notification     │
└────────┬───────┴──────┬───────┴────────┬────────┴─────────┬────────┘
         │              │                │                  │
         │              │                │                  │
         ▼              ▼                ▼                  ▼
┌─────────────────┐  ┌───────────┐  ┌───────────────┐  ┌───────────────┐
│  MongoDB Atlas  │  │ Amazon S3 │  │ Redis Cache   │  │ Message Queue │
└─────────────────┘  └───────────┘  └───────────────┘  └───────────────┘
         ▲                                 ▲
         │                                 │
         ▼                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          External Integrations                       │
├─────────────────┬───────────────────────┬─────────────────────────┬─┘
│ Parivaahan API  │ Testing Equipment API │ Payment Gateway         │
└─────────────────┴───────────────────────┴─────────────────────────┘
```

### Architecture Components

1. **Frontend Layer**: 
   - React.js-based Single Page Application (SPA)
   - Responsive design for various devices
   - Component-based architecture for reusability
   - State management using Redux for complex state handling
   - WebSocket integration for real-time updates

2. **API Gateway Layer**:
   - Centralized entry point for all client requests
   - Request routing to appropriate microservices
   - Authentication and authorization validation
   - Rate limiting and request throttling
   - Request/response transformation when needed

3. **Service Layer**:
   - Decomposed into domain-specific microservices
   - Each microservice handles specific business functionality
   - Services communicate via well-defined APIs
   - Independent deployment and scaling

4. **Data Layer**:
   - MongoDB for structured data storage
   - Amazon S3 for document and image storage
   - Redis for caching and session management
   - Message queuing for asynchronous processing

5. **Integration Layer**:
   - Connectors to external systems (Parivaahan portal)
   - Testing equipment integration through WebSockets
   - Payment gateway integration
   - Notification services (email, SMS)

## Technology Stack

### Backend
- **Primary Language**: Python 3.9+
- **Web Framework**: FastAPI for microservices
  - High performance, asynchronous capability
  - Built-in validation and documentation
- **Authentication**: JWT with refresh token mechanism
- **ORM**: Motor (async MongoDB driver) or ODM like Beanie
- **API Documentation**: OpenAPI/Swagger
- **WebSockets**: FastAPI WebSockets for real-time communication
- **Task Processing**: Celery with Redis as broker
- **Testing**: Pytest for unit and integration testing

### Frontend
- **Framework**: React.js with TypeScript
- **State Management**: Redux with Redux Toolkit
- **UI Component Library**: Material-UI or Ant Design
- **Form Handling**: Formik with Yup validation
- **HTTP Client**: Axios
- **WebSockets**: Socket.io client
- **Mapping**: Leaflet or Google Maps API
- **Charts/Visualization**: Recharts or D3.js
- **Testing**: Jest with React Testing Library

### Infrastructure
- **Database**: MongoDB Atlas (managed service)
- **Object Storage**: Amazon S3
- **Caching**: Redis
- **Containerization**: Docker
- **Container Orchestration**: Kubernetes
- **CI/CD**: GitHub Actions or Jenkins
- **Monitoring**: Prometheus with Grafana
- **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **API Gateway**: Kong or AWS API Gateway

## Security Architecture

Security is paramount for this system as it deals with official vehicle testing and certification. A comprehensive security approach will be implemented:

### Authentication System

The system will implement a robust token-based authentication using JWT (JSON Web Tokens) with a refresh token mechanism:

1. **Token-based Authentication Flow**:
   - User logs in with email/password
   - Server verifies credentials
   - Server generates:
     - Access token (short-lived, 15 minutes)
     - Refresh token (long-lived, 7 days)
   - Tokens are returned to the client
   - Client stores tokens (Access token in memory, Refresh token in secure HTTP-only cookie)

2. **Token Usage and Refresh Mechanism**:
   - Access token included in Authorization header for API requests
   - When access token expires, client uses refresh token to request new access token
   - Refresh token rotation on each use to prevent token theft

3. **Token Security Measures**:
   - Access tokens signed with RS256 algorithm (asymmetric)
   - Tokens include user ID, role, permissions, and expiration
   - Refresh tokens are stored in database with user reference and expiration
   - Ability to revoke refresh tokens for specific users or globally

4. **Multi-factor Authentication (MFA)**:
   - Optional MFA for critical roles (Admin, Transport Commissioner)
   - MFA via SMS or email one-time passwords (OTP)

### Data Security

1. **Data Encryption**:
   - Data encryption at rest in MongoDB and S3
   - TLS/SSL for all data in transit
   - End-to-end encryption for sensitive data

2. **Document Security**:
   - Secure pre-signed URLs for S3 document access
   - Time-limited document access
   - Document watermarking for traceability

3. **API Security**:
   - Input validation and sanitization
   - Protection against common attacks (SQL injection, XSS, CSRF)
   - Rate limiting and throttling to prevent abuse

4. **Network Security**:
   - Web Application Firewall (WAF)
   - DDoS protection
   - IP whitelisting for administrative access
   - Network segmentation for sensitive components

### Compliance Security

1. **Audit Trails**:
   - Comprehensive logging of all access and actions
   - Immutable audit logs for accountability
   - Regular audit log reviews

2. **Privacy Compliance**:
   - Data minimization and purpose limitation
   - User consent management
   - Configurable data retention policies

3. **Regulatory Alignment**:
   - Alignment with Indian IT Act and regulations
   - Digital signature compliance for official documents
   - Compliance with government data protection requirements

## Data Management Strategy

The ATS Networking Software will use a hybrid data storage approach to efficiently manage different types of data:

### MongoDB Data Management

MongoDB will be used to store structured data as outlined in the MongoDB schema provided. The schema design follows best practices for document databases:

1. **Database Design Principles**:
   - Proper document structure with appropriate nesting
   - Normalized references where appropriate
   - Efficient indexing strategy for performance
   - Data versioning for critical collections

2. **Data Access Patterns**:
   - Query optimization based on access patterns
   - Aggregation pipelines for complex reporting
   - Read/write concerns configured for data consistency

3. **Data Consistency**:
   - Transaction support for multi-document operations
   - Optimistic concurrency control
   - Constraints enforcement at application level

### Amazon S3 Storage Management

Amazon S3 will handle document and image storage with a well-defined organization structure:

1. **S3 Bucket Organization**:
   ```
   s3://ats-system/
     ├── documents/
     │   ├── ats-centers/{center-id}/
     │   │   ├── registration/
     │   │   └── approvals/
     │   └── users/{user-id}/
     ├── vehicles/
     │   └── {vehicle-number}/
     │       ├── number-plate/
     │       ├── test-images/
     │       └── documents/
     └── reports/
         ├── form69/{year}/{month}/
         └── certificates/{year}/{month}/
   ```

2. **Document Lifecycle Management**:
   - Automatic archiving of older documents
   - Versioning for critical documents
   - Retention policies aligned with regulatory requirements

3. **Access Management**:
   - Fine-grained access control with IAM policies
   - Temporary access via pre-signed URLs
   - Encryption of sensitive documents

### Cache Strategy

Redis will be used for caching frequently accessed data:

1. **Cache Layers**:
   - API response caching
   - Session data caching
   - Frequently accessed reference data

2. **Cache Invalidation**:
   - Time-based expiration
   - Event-based invalidation
   - Cache-aside pattern implementation

## User Management and Authentication

### Registration Process

1. **New User Registration Flow**:
   - ATS center registration form submission
   - Document upload to S3
   - Email verification
   - Admin review and approval
   - Role assignment
   - Account activation

2. **User Profile Management**:
   - Self-service profile updates
   - Password management
   - Contact information updates
   - Profile photo management

### Authentication Flow

1. **Login Process**:
   - Email and password authentication
   - JWT issuance (access + refresh tokens)
   - Role and permission loading
   - Login activity logging

2. **Password Management**:
   - Secure password reset workflow
   - Password policy enforcement
   - Password expiration and history
   - Account lockout after failed attempts

3. **Session Management**:
   - Inactive session timeout
   - Concurrent session handling
   - Forced logout capability
   - Session activity tracking

## Role-Based Access Control (RBAC)

The system will implement a flexible, service-based RBAC system that allows for role evolution without code changes:

### Permission Design

1. **Permission Structure**:
   - Permissions defined as `resource:action`
   - Examples: `vehicles:read`, `tests:approve`, `users:create`
   - Granular permissions for fine-tuned access control

2. **Role Definition**:
   - Roles as collections of permissions
   - Role hierarchy support
   - Role templates for common use cases

3. **Dynamic Permission Assignment**:
   - Permission assignment based on context
   - ATS center-specific permissions
   - Time-based or condition-based permissions

### Role Hierarchy

1. **Role Relationships**:
   - Super Admin (complete system access)
   - Transport Commissioner (state-level oversight)
   - Additional Transport Commissioner (deputy role)
   - RTO Officer (regional oversight, approval authority)
   - ATS Owner (center management)
   - ATS Center Admin (appointment management)
   - ATS Center Testing (test execution)

2. **Context-Based Access Control**:
   - Geographic restrictions (district, state)
   - Time-based restrictions
   - Workflow stage restrictions

### RBAC Implementation

1. **Technical Approach**:
   - Permissions stored in JWT claims
   - Permission verification middleware
   - UI element visibility based on permissions
   - API endpoint protection based on required permissions

2. **Permission Checking**:
   - Permission checks at API gateway
   - Secondary checks at service level
   - Attribute-based access control for complex scenarios

## Module Design

The system is divided into functional modules that align with business domains:

### Core Modules

1. **User Management Module**:
   - User registration and authentication
   - Profile management
   - Role and permission management

2. **ATS Center Management Module**:
   - Center registration and approval
   - Center details management
   - Testing equipment tracking

3. **Vehicle Management Module**:
   - Vehicle registration and validation
   - Document verification
   - Vehicle history tracking

4. **Appointment Management Module**:
   - Appointment scheduling
   - Payment processing
   - Schedule optimization

5. **Testing Module**:
   - Test execution and data collection
   - Real-time equipment integration
   - Test result processing

6. **Certification Module**:
   - Form 69 generation
   - Approval workflow
   - Certificate (Form 38) management

7. **Reporting and Analytics Module**:
   - Operational reports
   - Performance analytics
   - Compliance reporting

8. **Administration Module**:
   - System configuration
   - Master data management
   - System health monitoring

### Module Interactions

Each module will expose well-defined APIs for inter-module communication. Critical workflows will be implemented as orchestrated processes that span multiple modules:

1. **Vehicle Testing Workflow**:
   - Appointment confirmation
   - Vehicle check-in
   - Test sequence execution
   - Result compilation
   - Approval process
   - Certificate issuance

2. **ATS Center Onboarding Workflow**:
   - Registration
   - Document verification
   - Approval process
   - Equipment setup
   - Center activation

## Integration Architecture

The system will integrate with several external systems and components:

### External System Integrations

1. **Parivaahan Portal Integration**:
   - Appointment data retrieval
   - Vehicle information lookup
   - Certificate submission
   - Payment verification

2. **Testing Equipment Integration**:
   - Real-time data collection via WebSockets
   - Equipment calibration status monitoring
   - Measurement validation
   - Test procedure control

3. **Payment Gateway Integration**:
   - Secure payment processing
   - Transaction reconciliation
   - Receipt generation
   - Refund processing

### Integration Patterns

1. **API-Based Integration**:
   - RESTful APIs with OpenAPI specifications
   - Versioned APIs for backward compatibility
   - Rate-limited access
   - Circuit breaker pattern for resilience

2. **Event-Driven Integration**:
   - Message queues for asynchronous processing
   - Event publication for state changes
   - Event-driven workflows

3. **Real-Time Integration**:
   - WebSocket connections for live data
   - Pub/sub patterns for notifications
   - Real-time dashboards

## Performance Optimization

The system will be optimized for performance across all components:

### Database Optimization

1. **MongoDB Performance Tuning**:
   - Appropriate indexing strategy
   - Read/write concern optimization
   - Sharding for horizontal scaling
   - Query optimization and profiling

2. **Caching Strategy**:
   - Multi-level caching (application, database)
   - Cache warming for predictable loads
   - Intelligent cache invalidation

### Application Performance

1. **API Optimization**:
   - Response compression
   - Pagination for large result sets
   - Field filtering to reduce payload size
   - Batch processing for bulk operations

2. **Frontend Performance**:
   - Code splitting and lazy loading
   - Asset optimization and compression
   - Client-side caching
   - Progressive rendering

3. **Background Processing**:
   - Asynchronous task execution
   - Job prioritization and scheduling
   - Parallel processing where applicable

## Audit and Compliance

A comprehensive audit system will track all system activities for accountability and compliance:

### Audit Logging

1. **Audit Events**:
   - User authentication events
   - Data access and modifications
   - Administrative actions
   - System configuration changes
   - Test result approvals and rejections

2. **Audit Data Capture**:
   - Actor identification (user, system)
   - Action description
   - Timestamp (with timezone)
   - IP address and device information
   - Before/after state for changes
   - Context information

3. **Audit Storage**:
   - Immutable storage
   - Tamper-evident logging
   - Retention policy enforcement
   - Searchable and queryable logs

### Compliance Features

1. **Regulatory Compliance**:
   - Alignment with Motor Vehicles Act requirements
   - Digital signature compliance
   - Data retention compliance
   - Privacy protection measures

2. **Operational Compliance**:
   - Testing procedure enforcement
   - Mandatory field validation
   - Workflow compliance
   - Equipment calibration tracking

3. **Reporting Compliance**:
   - Standard compliance reports
   - Audit trail reporting
   - Exception reporting
   - Trend analysis

## Deployment Strategy

The system will be deployed using a modern containerized approach:

### Deployment Architecture

1. **Container Strategy**:
   - Microservices packaged as Docker containers
   - Kubernetes for orchestration
   - Helm charts for deployment configuration
   - Multi-stage builds for optimized images

2. **Environment Strategy**:
   - Development environment
   - Testing/QA environment
   - Staging environment
   - Production environment

3. **Infrastructure as Code**:
   - Terraform for infrastructure provisioning
   - Kubernetes manifests for service configuration
   - Configuration management via ConfigMaps and Secrets

### CI/CD Pipeline

1. **Continuous Integration**:
   - Automated code linting and style checking
   - Unit and integration testing
   - Static code analysis
   - Vulnerability scanning

2. **Continuous Delivery**:
   - Automated build process
   - Image versioning and tagging
   - Deployment to staging environment
   - Automated regression testing

3. **Deployment Process**:
   - Blue-green deployment strategy
   - Canary releases for risk mitigation
   - Automated rollback capability
   - Deployment approval workflow

## Monitoring and Logging

Comprehensive monitoring will ensure system health and performance:

### Monitoring Strategy

1. **Infrastructure Monitoring**:
   - Server resource utilization
   - Network performance
   - Database metrics
   - Storage utilization

2. **Application Monitoring**:
   - Service health checks
   - API response times
   - Error rates and patterns
   - User session metrics

3. **Business Metrics**:
   - Test throughput
   - Approval rates
   - Center utilization
   - User engagement

### Logging Framework

1. **Log Management**:
   - Centralized log collection
   - Structured logging format (JSON)
   - Log level configuration
   - Log rotation and retention

2. **Log Analysis**:
   - Real-time log search and filtering
   - Log correlation across services
   - Pattern recognition and anomaly detection
   - Alerting based on log patterns

### Alerting System

1. **Alert Configuration**:
   - Threshold-based alerts
   - Anomaly-based alerts
   - Alert prioritization
   - Alert routing and escalation

2. **Notification Channels**:
   - Email notifications
   - SMS alerts
   - Integration with incident management systems
   - On-call rotation management

## Disaster Recovery and Business Continuity

The system will be designed for resilience and continuity:

### Backup Strategy

1. **Data Backup**:
   - MongoDB regular snapshots
   - S3 cross-region replication
   - Database transaction logs
   - Incremental and full backups

2. **System Configuration Backup**:
   - Infrastructure configuration backups
   - Application configuration versioning
   - Secrets management with versioning

### Recovery Procedures

1. **Recovery Scenarios**:
   - Single service failure
   - Database corruption
   - Complete system failure
   - Regional outage

2. **Recovery Time Objectives (RTO)**:
   - Critical services: < 1 hour
   - Non-critical services: < 4 hours
   - Complete system: < 8 hours

3. **Recovery Point Objectives (RPO)**:
   - Critical data: < 5 minutes
   - Non-critical data: < 1 hour

## Scalability Considerations

The system will be designed to scale as demand grows:

### Horizontal Scaling

1. **Service Scalability**:
   - Stateless service design
   - Auto-scaling based on load
   - Load balancing across instances

2. **Database Scaling**:
   - MongoDB sharding for horizontal scaling
   - Read replicas for read-heavy workloads
   - Database connection pooling

### Vertical Scaling

1. **Resource Optimization**:
   - Efficient resource utilization
   - Performance tuning for high throughput
   - Memory and CPU optimization

### Geographic Distribution

1. **Multi-Region Strategy**:
   - Region-specific deployments
   - Geo-distributed database
   - Content delivery network for static assets

## Development Methodology

The development will follow modern software engineering practices:

### Agile Development

1. **Sprint Planning**:
   - Two-week sprint cycles
   - Feature prioritization
   - Story point estimation
   - Sprint retrospectives

2. **Development Practices**:
   - Test-driven development (TDD)
   - Pair programming for complex components
   - Code reviews for all changes
   - Continuous integration

### Code Quality

1. **Quality Assurance**:
   - Linting and static code analysis
   - Code coverage requirements
   - Performance testing
   - Security scanning

2. **Documentation**:
   - API documentation (OpenAPI)
   - Code documentation
   - Architecture documentation
   - User guides and tutorials

## Testing Strategy

A comprehensive testing approach will ensure system quality:

### Testing Levels

1. **Unit Testing**:
   - Component-level tests
   - Mocking of dependencies
   - Test coverage requirements

2. **Integration Testing**:
   - Service interaction testing
   - API contract testing
   - Database integration testing

3. **System Testing**:
   - End-to-end workflow testing
   - Performance testing
   - Security testing
   - Compatibility testing

4. **User Acceptance Testing**:
   - Stakeholder validation
   - Scenario-based testing
   - Usability testing

### Automated Testing

1. **Test Automation**:
   - Automated unit and integration tests
   - UI automation with Cypress or Playwright
   - API testing with Postman or similar tools
   - Load testing with JMeter or Locust

2. **Test Environment Management**:
   - Ephemeral test environments
   - Test data management
   - Environment parity with production

## Conclusion

The ATS Networking Software architecture outlined in this document provides a comprehensive, secure, and scalable approach to building a system that facilitates vehicle fitness testing across India. By leveraging modern technologies and best practices, the system will deliver a seamless experience for all stakeholders while ensuring compliance with regulatory requirements.

Key strengths of this architecture include:

1. **Robust Security**: Multi-layered security with token-based authentication, encryption, and comprehensive audit trails.

2. **Scalability**: Microservices architecture that allows independent scaling of components.

3. **Flexibility**: Service-based RBAC that can evolve without code changes.

4. **Integration Capabilities**: Well-defined integration points with external systems.

5. **Performance Optimization**: Caching, database optimization, and efficient API design.

6. **Compliance**: Comprehensive audit logging and alignment with regulatory requirements.

This architecture provides a solid foundation for developing a system that will serve the needs of testing centers, government officials, and vehicle owners while ensuring the integrity of the vehicle fitness testing process.

# ATS Software Architecture

## Overview
The ATS (Automated Testing Station) Network is a modular backend system designed to manage vehicle testing, reporting, and monitoring. It follows a microservices-inspired architecture with the following key components:

### 1. API Layer
- **Files**: `admin.py`, `analytics.py`, `auth.py`, `centers.py`, `monitoring.py`, `reports.py`, `tests.py`, `users.py`, `vehicles.py`
- **Purpose**: Expose RESTful APIs for managing users, vehicles, tests, and reports.

### 2. Core Layer
- **Files**: `base.py`, `dependencies.py`, `manager.py`, `middleware.py`, `rbac.py`, `token.py`, `config.py`, `constants.py`, `exception.py`, `init.py`, `redis.py`, `security.py`, `service.py`
- **Purpose**: Provide core functionalities like authentication, RBAC, database management, and middleware.

### 3. Database Layer
- **Files**: `manager.py`, `migration.py`, `query_optimizer.py`, `schemas.py`, `validator.py`
- **Purpose**: Handle database interactions, schema definitions, and migrations.

### 4. Models Layer
- **Files**: `audit.py`, `center.py`, `common.py`, `init.py`, `location.py`, `notification.py`, `reports.py`, `test.py`, `user.py`, `vehicle.py`
- **Purpose**: Define database models and relationships.

### 5. Services Layer
- **Files**: `authentication_service.py`, `cache_service.py`, `center_service.py`, `cleanup_service.py`, `document_service.py`, `error_handler.py`, `error_types.py`, `geolocation_service.py`, `error_monitoring.py`, `metrics_service.py`, `test_monitor.py`, `results_service.py`, `session_service.py`, `s3_service.py`, `queue_service.py`
- **Purpose**: Implement business logic and integrations (e.g., S3, Redis, notifications).

### 6. Utilities Layer
- **Files**: `date_utils.py`, `file_utils.py`, `location_utils.py`, `security_utils.py`, `transform_utils.py`, `validation_utils.py`
- **Purpose**: Provide reusable utility functions for date handling, file operations, security, and validation.

### 7. Main Application
- **Files**: `main.py`, `.env`, `config.py`, `inti_db.py`
- **Purpose**: Initialize the application, configure settings, and manage the application lifecycle.

## Missing Files
- **Router File**: `router.py` is missing in `app/api/v1/`. This file should include all API routes.
- **Database Initialization**: `init_db.py` exists but is named incorrectly as `inti_db.py`. Rename it for clarity.
- **Test Files**: Unit and integration test files are missing. Add a `tests/` directory with test cases.

## Next Steps
- Ensure all files listed above are present and correctly implemented.
- Add missing files and resolve inconsistencies in the codebase.
