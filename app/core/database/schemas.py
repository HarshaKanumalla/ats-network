# backend/app/core/database/schemas.py

from typing import Dict, Any
from datetime import datetime

class DatabaseSchemas:
    """Manages MongoDB collection schemas and validations."""
    
    @staticmethod
    def get_users_schema() -> Dict[str, Any]:
        """Get users collection schema validation."""
        return {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["email", "passwordHash", "role", "status", "createdAt"],
                "properties": {
                    "email": {
                        "bsonType": "string",
                        "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
                    },
                    "passwordHash": {"bsonType": "string"},
                    "role": {
                        "enum": ["transport_commissioner", "additional_commissioner", 
                                "rto_officer", "ats_owner", "ats_admin", "ats_testing"]
                    },
                    "status": {
                        "enum": ["pending", "active", "suspended", "inactive"]
                    },
                    "fullName": {"bsonType": "string"},
                    "phoneNumber": {
                        "bsonType": "string",
                        "pattern": "^\\+?[1-9]\\d{9,14}$"
                    },
                    "centerId": {"bsonType": ["objectId", "null"]},
                    "permissions": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "lastLogin": {"bsonType": ["date", "null"]},
                    "createdAt": {"bsonType": "date"},
                    "updatedAt": {"bsonType": "date"}
                }
            }
        }

    @staticmethod
    def get_centers_schema() -> Dict[str, Any]:
        """Get centers collection schema validation."""
        return {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["centerCode", "centerName", "address", "status", "createdAt"],
                "properties": {
                    "centerCode": {
                        "bsonType": "string",
                        "pattern": "^ATS\\d{6}$"
                    },
                    "centerName": {"bsonType": "string"},
                    "address": {
                        "bsonType": "object",
                        "required": ["street", "city", "state", "pinCode"],
                        "properties": {
                            "street": {"bsonType": "string"},
                            "city": {"bsonType": "string"},
                            "state": {"bsonType": "string"},
                            "pinCode": {
                                "bsonType": "string",
                                "pattern": "^\\d{6}$"
                            },
                            "coordinates": {
                                "bsonType": "object",
                                "required": ["type", "coordinates"],
                                "properties": {
                                    "type": {"enum": ["Point"]},
                                    "coordinates": {
                                        "bsonType": "array",
                                        "items": {"bsonType": "double"}
                                    }
                                }
                            }
                        }
                    },
                    "status": {
                        "enum": ["pending", "active", "suspended", "inactive"]
                    },
                    "testingEquipment": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["type", "serialNumber", "status"],
                            "properties": {
                                "type": {"bsonType": "string"},
                                "serialNumber": {"bsonType": "string"},
                                "status": {"enum": ["active", "maintenance", "inactive"]}
                            }
                        }
                    },
                    "createdAt": {"bsonType": "date"},
                    "updatedAt": {"bsonType": "date"}
                }
            }
        }

    @staticmethod
    def get_test_sessions_schema() -> Dict[str, Any]:
        """Get test sessions collection schema validation."""
        return {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["sessionCode", "vehicleId", "centerId", "status", "createdAt"],
                "properties": {
                    "sessionCode": {
                        "bsonType": "string",
                        "pattern": "^TS\\d{12}$"
                    },
                    "vehicleId": {"bsonType": "objectId"},
                    "centerId": {"bsonType": "objectId"},
                    "status": {
                        "enum": ["scheduled", "in_progress", "completed", "failed", "cancelled"]
                    },
                    "testResults": {
                        "bsonType": "object",
                        "properties": {
                            "speedTest": {"bsonType": ["object", "null"]},
                            "brakeTest": {"bsonType": ["object", "null"]},
                            "noiseTest": {"bsonType": ["object", "null"]},
                            "headlightTest": {"bsonType": ["object", "null"]},
                            "axleTest": {"bsonType": ["object", "null"]}
                        }
                    },
                    "operatorId": {"bsonType": "objectId"},
                    "startTime": {"bsonType": ["date", "null"]},
                    "endTime": {"bsonType": ["date", "null"]},
                    "createdAt": {"bsonType": "date"},
                    "updatedAt": {"bsonType": "date"}
                }
            }
        }

    @staticmethod
    def get_vehicles_schema() -> Dict[str, Any]:
        """Get vehicles collection schema validation."""
        return {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["registrationNumber", "vehicleType", "manufacturingYear", "createdAt"],
                "properties": {
                    "registrationNumber": {
                        "bsonType": "string",
                        "pattern": "^[A-Z]{2}\\d{2}[A-Z]{1,2}\\d{4}$"
                    },
                    "vehicleType": {
                        "enum": ["commercial", "private", "transport"]
                    },
                    "manufacturingYear": {
                        "bsonType": "int",
                        "minimum": 1900,
                        "maximum": 2025  # Update yearly
                    },
                    "ownerInfo": {
                        "bsonType": "object",
                        "required": ["name", "contact"],
                        "properties": {
                            "name": {"bsonType": "string"},
                            "contact": {"bsonType": "string"},
                            "email": {"bsonType": ["string", "null"]},
                            "address": {"bsonType": ["string", "null"]}
                        }
                    },
                    "lastTestDate": {"bsonType": ["date", "null"]},
                    "nextTestDue": {"bsonType": ["date", "null"]},
                    "testHistory": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["sessionId", "testDate", "status"],
                            "properties": {
                                "sessionId": {"bsonType": "objectId"},
                                "testDate": {"bsonType": "date"},
                                "status": {"enum": ["passed", "failed"]}
                            }
                        }
                    },
                    "createdAt": {"bsonType": "date"},
                    "updatedAt": {"bsonType": "date"}
                }
            }
        }

    @staticmethod
    def get_collection_indexes() -> Dict[str, List[Dict[str, Any]]]:
        """Get collection indexes configuration."""
        return {
            "users": [
                {"key": {"email": 1}, "unique": True},
                {"key": {"role": 1, "status": 1}},
                {"key": {"centerId": 1}}
            ],
            "centers": [
                {"key": {"centerCode": 1}, "unique": True},
                {"key": {"status": 1}},
                {"key": {"address.coordinates": "2dsphere"}
            ],
            "testSessions": [
                {"key": {"sessionCode": 1}, "unique": True},
                {"key": {"vehicleId": 1, "testDate": -1}},
                {"key": {"centerId": 1, "status": 1}},
                {"key": {"createdAt": -1}}
            ],
            "vehicles": [
                {"key": {"registrationNumber": 1}, "unique": True},
                {"key": {"lastTestDate": 1}},
                {"key": {"nextTestDue": 1}}
            ]
        }