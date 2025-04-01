# backend/app/api/v1/analytics.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from ...core.auth.permissions import RolePermission, require_permission
from ...core.security import get_current_user
from ...services.analytics.service import analytics_service
from ...services.center.service import center_service
from ...models.analytics import (
    AnalyticsResponse,
    TestAnalytics,
    CenterAnalytics,
    TrendAnalysis
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

class TestTrendsRequest(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    center_id: Optional[str] = Field(None, description="Center ID for filtering")

class PerformanceMetricsRequest(BaseModel):
    metric_type: str = Field(..., description="Type of metric to analyze")
    dimension: str = Field(..., description="Dimension for analysis")
    time_period: str = Field(..., regex="^(1m|3m|6m|1y)$", description="Valid time periods: 1m, 3m, 6m, 1y")

@router.get("/test/trends", response_model=AnalyticsResponse)
async def analyze_test_trends(
    request: TestTrendsRequest,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Analyze testing trends and patterns."""
    try:
        # Validate date range
        if request.start_date and request.end_date and request.end_date < request.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date"
            )

        # Apply role-based filtering
        if current_user.role != "transport_commissioner":
            if current_user.role == "ats_owner":
                request.center_id = str(current_user.center_id)
            elif not await center_service.can_access_center(
                user=current_user,
                center_id=request.center_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view these analytics"
                )

        analysis = await analytics_service.analyze_test_trends(
            start_date=request.start_date,
            end_date=request.end_date,
            center_id=request.center_id
        )

        logger.info(f"Test trends analyzed successfully for user {current_user.id}")
        return AnalyticsResponse(
            status="success",
            message="Test trends analyzed successfully",
            data=analysis
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test trend analysis error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze test trends"
        )

@router.get("/center/performance", response_model=CenterAnalytics)
async def analyze_center_performance(
    center_id: str,
    period_days: int = 30,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> CenterAnalytics:
    """Analyze center performance metrics."""
    try:
        # Verify center access
        if not await center_service.can_access_center(
            user=current_user,
            center_id=center_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view these analytics"
            )

        performance = await analytics_service.analyze_center_performance(
            center_id=center_id,
            period_days=period_days
        )

        logger.info(f"Center performance analyzed successfully for center {center_id}")
        return CenterAnalytics(
            status="success",
            message="Performance analyzed successfully",
            data=performance
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Performance analysis error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze center performance"
        )

@router.get("/regional/insights", response_model=AnalyticsResponse)
async def get_regional_insights(
    state: Optional[str] = None,
    district: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Get regional testing insights and patterns."""
    try:
        insights = await analytics_service.analyze_regional_data(
            state=state,
            district=district,
            user_role=current_user.role
        )

        logger.info(f"Regional insights generated successfully for user {current_user.id}")
        return AnalyticsResponse(
            status="success",
            message="Regional insights generated successfully",
            data=insights
        )

    except Exception as e:
        logger.error(f"Regional analysis error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate regional insights"
        )

@router.get("/vehicle/classifications", response_model=AnalyticsResponse)
async def analyze_vehicle_classifications(
    center_id: Optional[str] = None,
    time_period: str = "1m",
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Analyze vehicle classification patterns."""
    try:
        classifications = await analytics_service.analyze_vehicle_classifications(
            center_id=center_id,
            time_period=time_period,
            user_role=current_user.role
        )

        logger.info(f"Vehicle classifications analyzed successfully for user {current_user.id}")
        return AnalyticsResponse(
            status="success",
            message="Classification analysis completed successfully",
            data=classifications
        )

    except Exception as e:
        logger.error(f"Classification analysis error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze vehicle classifications"
        )

@router.get("/test/failure-patterns", response_model=AnalyticsResponse)
async def analyze_test_failures(
    center_id: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    time_period: str = "3m",
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Analyze test failure patterns and common issues."""
    try:
        failure_analysis = await analytics_service.analyze_failure_patterns(
            center_id=center_id,
            vehicle_type=vehicle_type,
            time_period=time_period,
            user_role=current_user.role
        )

        logger.info(f"Failure patterns analyzed successfully for user {current_user.id}")
        return AnalyticsResponse(
            status="success",
            message="Failure pattern analysis completed successfully",
            data=failure_analysis
        )

    except Exception as e:
        logger.error(f"Failure analysis error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze failure patterns"
        )

@router.get("/performance/metrics", response_model=AnalyticsResponse)
async def get_performance_metrics(
    request: PerformanceMetricsRequest,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Get detailed performance metrics and KPIs."""
    try:
        metrics = await analytics_service.get_performance_metrics(
            metric_type=request.metric_type,
            dimension=request.dimension,
            time_period=request.time_period,
            user_role=current_user.role
        )

        logger.info(f"Performance metrics retrieved successfully for user {current_user.id}")
        return AnalyticsResponse(
            status="success",
            message="Performance metrics retrieved successfully",
            data=metrics
        )

    except Exception as e:
        logger.error(f"Performance metrics error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )

@router.get("/trends/forecast", response_model=TrendAnalysis)
async def forecast_trends(
    metric: str,
    forecast_period: int = 30,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> TrendAnalysis:
    """Generate trend forecasts for specified metrics."""
    try:
        forecast = await analytics_service.generate_forecast(
            metric=metric,
            forecast_period=forecast_period,
            user_role=current_user.role
        )

        logger.info(f"Trend forecast generated successfully for metric {metric}")
        return TrendAnalysis(
            status="success",
            message="Trend forecast generated successfully",
            data=forecast
        )

    except Exception as e:
        logger.error(f"Trend forecast error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate trend forecast"
        )

@router.get("/reports/summary", response_model=AnalyticsResponse)
async def get_analytics_summary(
    report_type: str,
    time_period: str = "1m",
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Generate comprehensive analytics summary report."""
    try:
        summary = await analytics_service.generate_analytics_summary(
            report_type=report_type,
            time_period=time_period,
            user_role=current_user.role
        )

        logger.info(f"Analytics summary generated successfully for report type {report_type}")
        return AnalyticsResponse(
            status="success",
            message="Analytics summary generated successfully",
            data=summary
        )

    except Exception as e:
        logger.error(f"Analytics summary error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate analytics summary"
        )