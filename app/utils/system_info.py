"""System information utilities for tracking and managing application metadata.

This module provides centralized system information management, including version
tracking, deployment details, and system status monitoring. It maintains accurate
records of system configuration and operational parameters.
"""

from datetime import datetime
from typing import Dict, Any
import logging
import platform
import psutil
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class SystemInformation:
    """Manages system information and metadata tracking."""

    def __init__(self):
        """Initialize system information management."""
        self.initialization_time = datetime.utcnow()
        self._load_version_info()
        self._initialize_system_metadata()
        
        logger.info("System information tracking initialized")

    def _load_version_info(self) -> None:
        """Load application version information from configuration."""
        try:
            version_file = Path("version.json")
            if version_file.exists():
                with version_file.open() as f:
                    self.version_info = json.load(f)
            else:
                self.version_info = {
                    "version": "1.0.0",
                    "build_number": "development",
                    "last_updated": self.initialization_time.isoformat()
                }
                
            logger.info(f"Loaded version information: {self.version_info['version']}")
            
        except Exception as e:
            logger.error("Failed to load version information", exc_info=True)
            self.version_info = {
                "version": "unknown",
                "build_number": "error",
                "last_updated": self.initialization_time.isoformat()
            }

    def _initialize_system_metadata(self) -> None:
        """Initialize system metadata tracking."""
        try:
            self.system_metadata = {
                "python_version": platform.python_version(),
                "operating_system": f"{platform.system()} {platform.release()}",
                "cpu_cores": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "initialization_time": self.initialization_time.isoformat()
            }
            
            logger.info("System metadata initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize system metadata", exc_info=True)
            self.system_metadata = {
                "status": "initialization_failed",
                "initialization_time": self.initialization_time.isoformat()
            }

    def get_system_status(self) -> Dict[str, Any]:
        """Retrieve current system status information.

        This method provides comprehensive information about the current state
        of the system, including resource utilization and operational metrics.

        Returns:
            Dictionary containing system status information
        """
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            memory_info = psutil.virtual_memory()
            disk_info = psutil.disk_usage('/')

            return {
                "version_info": self.version_info,
                "system_metadata": self.system_metadata,
                "current_status": {
                    "cpu_usage_percent": cpu_usage,
                    "memory_usage_percent": memory_info.percent,
                    "disk_usage_percent": disk_info.percent,
                    "uptime_hours": self._calculate_uptime(),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
        except Exception as e:
            logger.error("Failed to retrieve system status", exc_info=True)
            return {
                "status": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "error_message": str(e)
            }

    def _calculate_uptime(self) -> float:
        """Calculate system uptime in hours.

        Returns:
            System uptime in hours
        """
        try:
            uptime_delta = datetime.utcnow() - self.initialization_time
            return round(uptime_delta.total_seconds() / 3600, 2)
        except Exception as e:
            logger.error("Failed to calculate uptime", exc_info=True)
            return 0.0

    def get_deployment_info(self) -> Dict[str, Any]:
        """Retrieve deployment configuration information.

        This method provides information about the current deployment
        configuration and environment settings.

        Returns:
            Dictionary containing deployment information
        """
        try:
            return {
                "environment": self.version_info.get("environment", "unknown"),
                "build_number": self.version_info.get("build_number", "unknown"),
                "deployment_date": self.version_info.get("last_updated", "unknown"),
                "system_configuration": {
                    "python_version": self.system_metadata["python_version"],
                    "operating_system": self.system_metadata["operating_system"]
                }
            }
            
        except Exception as e:
            logger.error("Failed to retrieve deployment information", exc_info=True)
            return {
                "status": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "error_message": str(e)
            }

# Initialize system information tracking
system_info = SystemInformation()