# MongoDB Schema Structure for Automated Testing Station (ATS) System

## Introduction
This document outlines the detailed MongoDB schema structure for the Automated Testing Station (ATS) system. Each collection is designed to support specific functionalities while maintaining data integrity and proper relationships between different components of the system.

## Schema Structure

### 1. Users Collection
This collection manages all user accounts and their access rights within the system.

```javascript
{
  _id: ObjectId,
  email: String,
  passwordHash: String,
  role: String, // ["super_admin", "transport_commissioner", "additional_commissioner", "rto_officer", "ats_owner", "ats_admin", "ats_testing"]
  firstName: String,
  lastName: String,
  phoneNumber: String,
  status: String, // ["active", "pending", "suspended"]
  createdAt: Date,
  updatedAt: Date,
  lastLogin: Date,
  atsCenter: ObjectId, // Reference to ATS Centers collection (null for higher officials)
  permissions: [String] // Array of specific permissions
}
```

Purpose: Manages user authentication, authorization, and profile information. The role field determines access levels, while the status field helps manage account states.

### 2. ATS Centers Collection
This collection stores information about individual testing centers and their equipment.

```javascript
{
  _id: ObjectId,
  centerName: String,
  centerCode: String, // Unique identifier for the center
  address: {
    street: String,
    city: String,
    district: String,
    state: String,
    pinCode: String,
    coordinates: {
      latitude: Number,
      longitude: Number
    }
  },
  status: String, // ["active", "inactive", "suspended"]
  owner: {
    userId: ObjectId, // Reference to Users collection
    documents: [{
      type: String,
      fileUrl: String,
      verificationStatus: String,
      uploadedAt: Date
    }]
  },
  testingEquipment: [{
    type: String, // ["speed", "brake", "noise", "headlight", "axle"]
    serialNumber: String,
    lastCalibration: Date,
    nextCalibration: Date,
    status: String
  }],
  createdAt: Date,
  updatedAt: Date
}
```

Purpose: Maintains comprehensive information about testing centers, including location, ownership, documentation, and equipment details.

### 3. Vehicles Collection
This collection manages information about vehicles that undergo testing.

```javascript
{
  _id: ObjectId,
  registrationNumber: String,
  vehicleType: String,
  manufacturingYear: Number,
  lastTestDate: Date,
  nextTestDue: Date,
  ownerInfo: {
    name: String,
    contact: String,
    address: String
  },
  documentVerification: {
    rcCard: {
      documentNumber: String,
      expiryDate: Date,
      verificationStatus: String
    },
    fitnessCard: {
      documentNumber: String,
      expiryDate: Date,
      verificationStatus: String
    },
    additionalDocuments: [{
      type: String,
      documentNumber: String,
      verificationStatus: String
    }]
  }
}
```

Purpose: Stores vehicle and owner information, tracking test history and document verification status.

### 4. Test Sessions Collection
This collection records detailed information about each testing session.

```javascript
{
  _id: ObjectId,
  vehicleId: ObjectId, // Reference to Vehicles collection
  atsCenterId: ObjectId, // Reference to ATS Centers collection
  sessionCode: String, // Unique identifier for the test session
  testDate: Date,
  status: String, // ["scheduled", "in_progress", "completed", "failed"]
  testedBy: ObjectId, // Reference to Users collection
  reviewedBy: ObjectId, // Reference to Users collection (ATS Admin)
  approvedBy: ObjectId, // Reference to Users collection (RTO Officer)
  testResults: {
    visualInspection: {
      numberPlate: {
        imageUrl: String,
        status: String,
        notes: String
      },
      reflectiveTape: {
        imageUrl: String,
        status: String,
        notes: String
      },
      sideMirrors: {
        imageUrl: String,
        status: String,
        notes: String
      },
      additionalImages: [{
        type: String,
        imageUrl: String,
        status: String,
        notes: String
      }]
    },
    speedTest: {
      maxSpeed: Number,
      targetSpeed: Number,
      status: String,
      timestamp: Date
    },
    accelerationTest: {
      acceleration: Number,
      timeElapsed: Number,
      status: String,
      timestamp: Date
    },
    brakeTest: {
      brakeForce: Number,
      imbalanceFinal: Number,
      imbalanceMax: Number,
      decelerationStatic: Number,
      decelerationDynamic: Number,
      status: String,
      timestamp: Date
    },
    noiseTest: {
      readings: [{
        value: Number,
        unit: String
      }],
      status: String,
      timestamp: Date
    },
    headlightTest: {
      pitchAngle: Number,
      yawAngle: Number,
      rollAngle: Number,
      breakPointX: Number,
      breakPointY: Number,
      intensity: Number,
      glare: Number,
      status: String,
      timestamp: Date
    },
    axleTest: {
      readings: [{
        axleNumber: Number,
        measurement: Number,
        status: String
      }],
      status: String,
      timestamp: Date
    }
  },
  finalResult: {
    status: String, // ["pass", "fail"]
    certificate: {
      certificateNumber: String,
      issueDate: Date,
      validUntil: Date,
      documentUrl: String
    },
    remarks: String
  },
  createdAt: Date,
  updatedAt: Date
}
```

Purpose: Maintains comprehensive records of all tests performed on vehicles, including detailed measurements and results for each test type.

### 5. Appointments Collection
This collection manages testing appointments and scheduling.

```javascript
{
  _id: ObjectId,
  vehicleId: ObjectId, // Reference to Vehicles collection
  atsCenterId: ObjectId, // Reference to ATS Centers collection
  appointmentDate: Date,
  timeSlot: String,
  status: String, // ["scheduled", "confirmed", "completed", "cancelled"]
  paymentStatus: String,
  paymentDetails: {
    amount: Number,
    transactionId: String,
    paymentDate: Date
  },
  createdAt: Date,
  updatedAt: Date
}
```

Purpose: Handles appointment scheduling and payment tracking for vehicle testing sessions.

### 6. Notifications Collection
This collection manages system notifications for all users.

```javascript
{
  _id: ObjectId,
  recipientId: ObjectId, // Reference to Users collection
  type: String, // ["test_complete", "approval_required", "appointment", "system"]
  title: String,
  message: String,
  relatedTo: {
    type: String, // ["vehicle", "test", "appointment"]
    id: ObjectId
  },
  status: String, // ["unread", "read"]
  createdAt: Date,
  readAt: Date
}
```

Purpose: Handles system-wide notifications and alerts for various events and actions.

### 7. Audit Logs Collection
This collection maintains a record of all system activities.

```javascript
{
  _id: ObjectId,
  userId: ObjectId, // Reference to Users collection
  action: String,
  entityType: String, // ["vehicle", "test", "user", "center"]
  entityId: ObjectId,
  changes: {
    before: Object,
    after: Object
  },
  ipAddress: String,
  timestamp: Date
}
```

Purpose: Provides comprehensive audit trailing for all significant actions within the system.

## Data Relationships

The collections maintain relationships through ObjectId references:

1. Users → ATS Centers: Through atsCenter field in Users collection
2. Test Sessions → Users: Through testedBy, reviewedBy, and approvedBy fields
3. Test Sessions → Vehicles: Through vehicleId field
4. Test Sessions → ATS Centers: Through atsCenterId field
5. Appointments → Vehicles and ATS Centers: Through respective ID fields
6. Notifications → Users: Through recipientId field
7. Audit Logs → Users: Through userId field

## Notes on Implementation

1. All date fields should use UTC timezone
2. ObjectId references ensure proper data relationships
3. Status fields use predefined string values for consistency
4. Nested objects are used where logical grouping is beneficial
5. Arrays are used for multiple related items
6. Timestamps (createdAt, updatedAt) track record history

