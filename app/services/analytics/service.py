# backend/app/services/analytics/service.py

"""
Service for analyzing test data, center performance, and system metrics.
Provides comprehensive analytics and insights.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
from bson import ObjectId
import pandas as pd
import numpy as np

from ...core.exceptions import AnalyticsError
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AnalyticsService:
    """Service for data analytics and insights generation."""
    
    def __init__(self):
        """Initialize analytics service."""
        self.db = None
        logger.info("Analytics service initialized")

    async def analyze_test_trends(
        self,
        center_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Analyze test result trends and patterns."""
        try:
            db = await get_database()
            
            # Build query
            query = {}
            if center_id:
                query["atsCenterId"] = ObjectId(center_id)
            if start_date and end_date:
                query["testDate"] = {"$gte": start_date, "$lte": end_date}
            
            # Aggregate test data
            pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": {
                            "year": {"$year": "$testDate"},
                            "month": {"$month": "$testDate"}
                        },
                        "total_tests": {"$sum": 1},
                        "pass_rate": {
                            "$avg": {
                                "$cond": [
                                    {"$eq": ["$status", "passed"]},
                                    1,
                                    0
                                ]
                            }
                        },
                        "average_duration": {"$avg": "$duration"}
                    }
                },
                {"$sort": {"_id.year": 1, "_id.month": 1}}
            ]
            
            results = await db.testSessions.aggregate(pipeline).to_list(None)
            
            # Process results
            trends = {
                "monthly_trends": results,
                "summary_statistics": await self._calculate_summary_statistics(results),
                "analysis_period": {
                    "start_date": start_date,
                    "end_date": end_date
                }
            }
            
            return trends
            
        except Exception as e:
            logger.error(f"Trend analysis error: {str(e)}")
            raise AnalyticsError("Failed to analyze test trends")

    async def analyze_center_performance(
        self,
        center_id: str,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """Analyze center performance metrics."""
        try:
            db = await get_database()
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=period_days)
            
            # Get performance metrics
            metrics = await self._get_center_metrics(
                db,
                center_id,
                start_date,
                end_date
            )
            
            # Calculate performance indicators
            performance_indicators = await self._calculate_performance_indicators(
                metrics
            )
            
            # Get comparative analysis
            comparison = await self._get_comparative_analysis(
                db,
                center_id,
                metrics
            )
            
            return {
                "metrics": metrics,
                "performance_indicators": performance_indicators,
                "comparative_analysis": comparison,
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                }
            }
            
        except Exception as e:
            logger.error(f"Performance analysis error: {str(e)}")
            raise AnalyticsError("Failed to analyze center performance")

    async def generate_insights(
        self,
        data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate actionable insights from analytics data."""
        try:
            insights = []
            
            # Analyze trends
            if trend_insight := await self._analyze_trend_patterns(data):
                insights.append(trend_insight)
            
            # Analyze performance
            if performance_insight := await self._analyze_performance_patterns(data):
                insights.append(performance_insight)
            
            # Analyze anomalies
            if anomaly_insight := await self._detect_anomalies(data):
                insights.append(anomaly_insight)
            
            return insights
            
        except Exception as e:
            logger.error(f"Insight generation error: {str(e)}")
            raise AnalyticsError("Failed to generate insights")

    async def _calculate_summary_statistics(
        self,
        data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate summary statistics from data."""
        try:
            if not data:
                return {}
            
            values = [item for item in data if "total_tests" in item]
            
            return {
                "total_count": sum(v["total_tests"] for v in values),
                "average_pass_rate": np.mean([v["pass_rate"] for v in values]),
                "std_dev_pass_rate": np.std([v["pass_rate"] for v in values]),
                "average_duration": np.mean([v["average_duration"] for v in values])
            }
            
        except Exception as e:
            logger.error(f"Statistics calculation error: {str(e)}")
            return {}

# Initialize analytics service
analytics_service = AnalyticsService()