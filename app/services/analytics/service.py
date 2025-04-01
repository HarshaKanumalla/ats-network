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
            metrics = await self._get_center_metrics(db, center_id, start_date, end_date)
            
            # Calculate performance indicators
            performance_indicators = await self._calculate_performance_indicators(metrics)
            
            # Get comparative analysis
            comparison = await self._get_comparative_analysis(db, center_id, metrics)
            
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

    async def _get_center_metrics(
        self,
        db,
        center_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get comprehensive center performance metrics."""
        pipeline = [
            {
                "$match": {
                    "atsCenterId": ObjectId(center_id),
                    "testDate": {"$gte": start_date, "$lte": end_date}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_tests": {"$sum": 1},
                    "passed_tests": {
                        "$sum": {"$cond": [{"$eq": ["$status", "passed"]}, 1, 0]}
                    },
                    "failed_tests": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "average_duration": {"$avg": "$duration"},
                    "total_revenue": {"$sum": "$testFee"},
                    "unique_vehicles": {"$addToSet": "$vehicleId"},
                    "unique_inspectors": {"$addToSet": "$inspectorId"}
                }
            }
        ]
        
        result = await db.testSessions.aggregate(pipeline).next()
        if not result:
            return {}
            
        return {
            "total_tests": result["total_tests"],
            "pass_rate": result["passed_tests"] / result["total_tests"],
            "average_duration": result["average_duration"],
            "revenue": result["total_revenue"],
            "unique_vehicles_tested": len(result["unique_vehicles"]),
            "active_inspectors": len(result["unique_inspectors"])
        }

    async def _calculate_performance_indicators(
        self,
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate key performance indicators."""
        if not metrics:
            return {}
            
        # Calculate efficiency score (0-100)
        efficiency = min(100, (
            (metrics["pass_rate"] * 40) +
            (min(1, 480 / metrics["average_duration"]) * 30) +
            (min(1, metrics["total_tests"] / (metrics["active_inspectors"] * 20)) * 30)
        ))
        
        # Calculate utilization rate
        utilization = metrics["total_tests"] / (
            metrics["active_inspectors"] * 8 * 30
        )  # Assuming 8 tests per day capacity
        
        return {
            "efficiency_score": round(efficiency, 2),
            "utilization_rate": round(utilization, 2),
            "revenue_per_test": round(
                metrics["revenue"] / metrics["total_tests"], 2
            ),
            "tests_per_inspector": round(
                metrics["total_tests"] / metrics["active_inspectors"], 2
            )
        }

    async def _get_comparative_analysis(
        self,
        db,
        center_id: str,
        center_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare center performance with others."""
        pipeline = [
            {
                "$group": {
                    "_id": "$atsCenterId",
                    "total_tests": {"$sum": 1},
                    "passed_tests": {
                        "$sum": {"$cond": [{"$eq": ["$status", "passed"]}, 1, 0]}
                    },
                    "average_duration": {"$avg": "$duration"}
                }
            },
            {
                "$project": {
                    "pass_rate": {"$divide": ["$passed_tests", "$total_tests"]},
                    "average_duration": 1,
                    "total_tests": 1
                }
            }
        ]
        
        all_centers = await db.testSessions.aggregate(pipeline).to_list(None)
        
        if not all_centers:
            return {}
        
        # Calculate percentiles
        pass_rates = [c["pass_rate"] for c in all_centers]
        durations = [c["average_duration"] for c in all_centers]
        volumes = [c["total_tests"] for c in all_centers]
        
        return {
            "pass_rate_percentile": np.percentile(
                pass_rates,
                np.searchsorted(pass_rates, center_metrics["pass_rate"]) * 100 / len(pass_rates)
            ),
            "efficiency_percentile": np.percentile(
                durations,
                (len(durations) - np.searchsorted(durations, center_metrics["average_duration"])) * 100 / len(durations)
            ),
            "volume_percentile": np.percentile(
                volumes,
                np.searchsorted(volumes, center_metrics["total_tests"]) * 100 / len(volumes)
            )
        }

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

    async def _analyze_trend_patterns(
        self,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Analyze patterns in trend data."""
        try:
            if not data.get("monthly_trends"):
                return None
                
            df = pd.DataFrame(data["monthly_trends"])
            
            # Calculate trend indicators
            trend_slope = np.polyfit(
                range(len(df)), 
                df["pass_rate"], 
                1
            )[0]
            
            # Detect seasonality using autocorrelation
            acf = pd.Series(df["total_tests"]).autocorr()
            
            return {
                "insight_type": "trend",
                "trend_direction": "increasing" if trend_slope > 0 else "decreasing",
                "trend_strength": abs(trend_slope),
                "seasonality_detected": acf > 0.7,
                "confidence": min(1.0, abs(trend_slope) * 10)
            }
            
        except Exception as e:
            logger.error(f"Trend pattern analysis error: {str(e)}")
            return None

    async def _analyze_performance_patterns(
        self,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Analyze performance patterns."""
        try:
            if not data.get("metrics"):
                return None
                
            metrics = data["metrics"]
            indicators = data.get("performance_indicators", {})
            
            insights = []
            
            # Analyze efficiency
            if indicators.get("efficiency_score", 0) < 70:
                insights.append({
                    "aspect": "efficiency",
                    "severity": "high",
                    "recommendation": "Review test procedures and staff training"
                })
            
            # Analyze utilization
            if indicators.get("utilization_rate", 0) < 0.6:
                insights.append({
                    "aspect": "utilization",
                    "severity": "medium",
                    "recommendation": "Consider optimizing resource allocation"
                })
            
            if not insights:
                return None
                
            return {
                "insight_type": "performance",
                "findings": insights,
                "impact_score": len(insights) * 0.5
            }
            
        except Exception as e:
            logger.error(f"Performance pattern analysis error: {str(e)}")
            return None

    async def _detect_anomalies(
        self,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detect anomalies in performance data."""
        try:
            if not data.get("metrics"):
                return None
                
            metrics = data["metrics"]
            anomalies = []
            
            # Check for statistical anomalies
            if metrics["pass_rate"] < 0.5:
                anomalies.append({
                    "metric": "pass_rate",
                    "value": metrics["pass_rate"],
                    "severity": "high"
                })
                
            if metrics["average_duration"] > 1200:  # 20 minutes
                anomalies.append({
                    "metric": "duration",
                    "value": metrics["average_duration"],
                    "severity": "medium"
                })
                
            if not anomalies:
                return None
                
            return {
                "insight_type": "anomaly",
                "anomalies": anomalies,
                "recommendations": [
                    f"Investigate {a['metric']} anomaly"
                    for a in anomalies
                ]
            }
            
        except Exception as e:
            logger.error(f"Anomaly detection error: {str(e)}")
            return None

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

    def _handle_analysis_error(
        self,
        error: Exception,
        context: str
    ) -> Dict[str, Any]:
        """Handle analysis errors with context."""
        error_msg = f"Analysis error in {context}: {str(error)}"
        logger.error(error_msg)
        return {
            "error": True,
            "context": context,
            "message": error_msg,
            "timestamp": datetime.utcnow()
        }

# Initialize analytics service
analytics_service = AnalyticsService()