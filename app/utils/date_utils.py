from datetime import datetime, timedelta
from typing import Optional

class DateUtils:
    """Utility functions for date handling."""
    
    @staticmethod
    def parse_date_string(date_str: str, fmt: str = '%Y-%m-%d') -> Optional[datetime]:
        """
        Parse a date string into a datetime object.
        
        Args:
            date_str (str): The date string to parse.
            fmt (str): The format of the date string. Default is '%Y-%m-%d'.
        
        Returns:
            Optional[datetime]: The parsed datetime object, or None if parsing fails.
        """
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def format_date(date: Optional[datetime], fmt: str = '%Y-%m-%d') -> Optional[str]:
        """
        Format a datetime object into a string.
        
        Args:
            date (Optional[datetime]): The datetime object to format.
            fmt (str): The format to use. Default is '%Y-%m-%d'.
        
        Returns:
            Optional[str]: The formatted date string, or None if the input is invalid.
        """
        if not date:
            return None
        try:
            return date.strftime(fmt)
        except Exception:
            return None

    @staticmethod
    def get_age_years(manufacture_date: datetime) -> int:
        """
        Calculate the age in years from the given manufacture date.
        
        Args:
            manufacture_date (datetime): The manufacture date.
        
        Returns:
            int: The age in years.
        """
        today = datetime.utcnow()
        age = today.year - manufacture_date.year
        # Adjust if today's date is before the manufacture date in the same year
        if (today.month, today.day) < (manufacture_date.month, manufacture_date.day):
            age -= 1
        return age

    @staticmethod
    def add_days(date: datetime, days: int) -> datetime:
        """
        Add a specified number of days to a date.
        
        Args:
            date (datetime): The original date.
            days (int): The number of days to add.
        
        Returns:
            datetime: The new date.
        """
        return date + timedelta(days=days)

    @staticmethod
    def subtract_days(date: datetime, days: int) -> datetime:
        """
        Subtract a specified number of days from a date.
        
        Args:
            date (datetime): The original date.
            days (int): The number of days to subtract.
        
        Returns:
            datetime: The new date.
        """
        return date - timedelta(days=days)

    @staticmethod
    def days_between(date1: datetime, date2: datetime) -> int:
        """
        Calculate the number of days between two dates.
        
        Args:
            date1 (datetime): The first date.
            date2 (datetime): The second date.
        
        Returns:
            int: The number of days between the two dates.
        """
        return abs((date2 - date1).days)

    @staticmethod
    def is_past_date(date: datetime) -> bool:
        """
        Check if a given date is in the past.
        
        Args:
            date (datetime): The date to check.
        
        Returns:
            bool: True if the date is in the past, False otherwise.
        """
        return date < datetime.utcnow()

    @staticmethod
    def is_future_date(date: datetime) -> bool:
        """
        Check if a given date is in the future.
        
        Args:
            date (datetime): The date to check.
        
        Returns:
            bool: True if the date is in the future, False otherwise.
        """
        return date > datetime.utcnow()