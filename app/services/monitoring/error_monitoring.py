# backend/app/services/monitoring/error_monitoring.py

from typing import Dict, Any, Optional
from datetime import datetime
import logging
from ..error_handler.error_types import TestMonitoringError

logger = logging.getLogger(__name__)

class ErrorMonitor:
    """Monitor and track system errors."""

    def __init__(self):
        """Initialize error monitoring."""
        self.error_thresholds = {
            "critical": 5,      # Critical errors per minute
            "validation": 10,   # Validation errors per minute
            "connection": 20    # Connection errors per minute
        }
        self.error_counts: Dict[str, int] = {}
        self.last_reset = datetime.utcnow()

    async def track_error(
        self,
        error: Exception,
        severity: str = "error",
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Track error occurrence and trigger alerts if thresholds exceeded."""
        try:
            # Reset counters if minute has passed
            current_time = datetime.utcnow()
            if (current_time - self.last_reset).seconds >= 60:
                self.error_counts = {}
                self.last_reset = current_time

            # Update error count
            error_type = error.__class__.__name__
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

            # Check thresholds
            await self._check_thresholds(error_type, severity, context)

            # Log error with context
            logger.error(
                f"Error tracked: {error_type}",
                extra={
                    "severity": severity,
                    "context": context,
                    "error_message": str(error),
                    "timestamp": current_time.isoformat()
                }
            )

        except Exception as e:
            logger.critical(f"Error monitoring failure: {str(e)}")

    async def _check_thresholds(
        self,
        error_type: str,
        severity: str,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Check if error thresholds have been exceeded."""
        try:
            if severity in self.error_thresholds:
                threshold = self.error_thresholds[severity]
                if self.error_counts.get(error_type, 0) >= threshold:
                    await self._trigger_alert(error_type, severity, context)

        except Exception as e:
            logger.error(f"Threshold check failure: {str(e)}")

    async def _trigger_alert(
        self,
        error_type: str,
        severity: str,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Trigger alerts for threshold violations."""
        try:
            alert_data = {
                "type": "error_threshold_exceeded",
                "error_type": error_type,
                "severity": severity,
                "count": self.error_counts[error_type],
                "threshold": self.error_thresholds[severity],
                "context": context,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Log alert
            logger.critical("Error threshold exceeded", extra=alert_data)

            # Here you would typically:
            # 1. Send notifications to administrators
            # 2. Update monitoring dashboards
            # 3. Trigger any automated response mechanisms

        except Exception as e:
            logger.critical(f"Alert trigger failure: {str(e)}")

# Initialize error monitoring
error_monitor = ErrorMonitor()