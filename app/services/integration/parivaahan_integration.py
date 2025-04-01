import requests
from typing import Dict, Any
from fastapi import HTTPException

class ParivaahanIntegrationService:
    BASE_URL = "https://parivaahan.gov.in/api/v1"  # Replace with the actual API URL

    @staticmethod
    def validate_vehicle_registration(registration_number: str) -> Dict[str, Any]:
        """
        Validate vehicle registration details using the Parivaahan API.
        """
        try:
            response = requests.get(
                f"{ParivaahanIntegrationService.BASE_URL}/validate",
                params={"registration_number": registration_number},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Parivaahan API error: {response.text}"
                )
        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to Parivaahan API: {str(e)}"
            )