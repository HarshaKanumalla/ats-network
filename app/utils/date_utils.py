# backend/app/utils/date_utils.py

from datetime import datetime, timedelta
from typing import Optional

class DateUtils:
    """Utility functions for date handling."""
    
    @staticmethod
    def parse_date_string(date_str: str, fmt: str = '%Y-%m-%d') -> Optional[datetime]:
        """Parse date string to datetime object."""
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def format_date(date: datetime, fmt: str = '%Y-%m-%d') -> str:
        """Format datetime object to string."""
        return date.strftime(fmt)

    @staticmethod
    def get_age_years(manufacture_date: datetime) -> int:
        """Calculate vehicle age in years."""
        today = datetime.utcnow()
        return today.year - manufacture_date.year