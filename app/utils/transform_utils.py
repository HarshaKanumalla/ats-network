# backend/app/utils/transform_utils.py

from typing import Dict, Any, List
from datetime import datetime

class TransformUtils:
    """Utility functions for data transformation."""
    
    @staticmethod
    def format_test_results(raw_results: Dict[str, Any]) -> Dict[str, Any]:
        """Format raw test results for response."""
        formatted = {}
        for test_type, results in raw_results.items():
            if test_type == 'speed_test':
                formatted['speedTest'] = {
                    'actualSpeed': results.get('actual_speed', 0),
                    'targetSpeed': results.get('target_speed', 60),
                    'deviation': results.get('deviation', 0),
                    'status': results.get('status', 'pending')
                }
            # Add other test type transformations as needed
        return formatted

    @staticmethod
    def format_vehicle_data(vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format vehicle data for response."""
        return {
            'registrationNumber': vehicle_data.get('registration_number'),
            'vehicleType': vehicle_data.get('vehicle_type'),
            'manufacturingYear': vehicle_data.get('manufacturing_year'),
            'ownerInfo': vehicle_data.get('owner_info', {}),
            'lastTestDate': vehicle_data.get('last_test_date'),
            'nextTestDue': vehicle_data.get('next_test_due'),
            'status': vehicle_data.get('status', 'pending')
        }
