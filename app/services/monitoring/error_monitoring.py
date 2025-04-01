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
            "ValidationError": 10,  # Validation errors per minute
            "ConnectionError": 20,  # Connection errors per minute
            "CriticalError": 5      # Critical errors per minute
        }
        self.error_counts: Dict[str, Dict[str, Any]] = {}  # {error_type: {"count": int, "last_reset": datetime}}
        self.last_reset = datetime.utcnow()

    async def track_error(
        self,
        error: Exception,
        severity: str = "error",
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track error occurrence and trigger alerts if thresholds exceeded.

        Args:
            error (Exception): The error to track.
            severity (str): The severity level of the error (e.g., "critical", "validation").
            context (Optional[Dict[str, Any]]): Additional context for the error.

        Returns:
            None
        """
        try:
            # Validate error object
            if not isinstance(error, Exception):
                logger.error("Invalid error object provided")
                return

            # Validate context
            if context and not isinstance(context, dict):
                logger.warning(f"Invalid context provided for error: {error.__class__.__name__}")
                context = {}

            # Reset counters if minute has passed
            current_time = datetime.utcnow()
            for error_type, data in list(self.error_counts.items()):
                if (current_time - data["last_reset"]).seconds >= 60:
                    del self.error_counts[error_type]

            # Update error count
            error_type = error.__class__.__name__
            if error_type not in self.error_counts:
                self.error_counts[error_type] = {"count": 0, "last_reset": current_time}
            self.error_counts[error_type]["count"] += 1

            # Check thresholds
            await self._check_thresholds(error_type, severity, context)

            # Log error with context
            logger.error(
                f"Error tracked: {error_type} with severity {severity}",
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
            if error_type in self.error_thresholds:
                threshold = self.error_thresholds[error_type]
                if self.error_counts[error_type]["count"] >= threshold:
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
                "count": self.error_counts[error_type]["count"],
                "threshold": self.error_thresholds.get(error_type, 0),
                "context": context,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Log alert
            logger.critical("Error threshold exceeded", extra=alert_data)

            # Placeholder for alert mechanisms
            await self._send_alert_notification(alert_data)

        except Exception as e:
            logger.critical(f"Alert trigger failure: {str(e)}")

    async def _send_alert_notification(self, alert_data: Dict[str, Any]) -> None:
        """Send alert notifications to administrators."""
        try:
            # Example: Integrate with an email or notification service
            logger.info(f"Sending alert notification: {alert_data}")
        except Exception as e:
            logger.error(f"Failed to send alert notification: {str(e)}")

# Initialize error monitoring
error_monitor = ErrorMonitor()