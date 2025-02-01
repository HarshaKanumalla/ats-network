from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from bson import ObjectId

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

@router.get("/test/trends", response_model=AnalyticsResponse)
async def analyze_test_trends(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    center_id: Optional[str] = None,
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Analyze testing trends and patterns.
    
    Args:
        start_date: Optional analysis start date
        end_date: Optional analysis end date
        center_id: Optional center ID for filtering
        current_user: Authenticated user
        
    Returns:
        Comprehensive test trend analysis
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        # Validate date range
        if start_date and end_date and end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date"
            )

        # Apply role-based filtering
        if current_user.role != "transport_commissioner":
            if current_user.role == "ats_owner":
                center_id = str(current_user.center_id)
            elif not await center_service.can_access_center(
                user=current_user,
                center_id=center_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view these analytics"
                )

        analysis = await analytics_service.analyze_test_trends(
            start_date=start_date,
            end_date=end_date,
            center_id=center_id
        )

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
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> CenterAnalytics:
    """Analyze center performance metrics.
    
    Args:
        center_id: ID of center to analyze
        period_days: Analysis period in days
        current_user: Authenticated user
        
    Returns:
        Center performance analytics
        
    Raises:
        HTTPException: If analysis fails
    """
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
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Get regional testing insights and patterns.
    
    Args:
        state: Optional state filter
        district: Optional district filter
        current_user: Authenticated user
        
    Returns:
        Regional analytics and insights
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        insights = await analytics_service.analyze_regional_data(
            state=state,
            district=district,
            user_role=current_user.role
        )

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
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Analyze vehicle classification patterns.
    
    Args:
        center_id: Optional center ID for filtering
        time_period: Analysis time period (1m, 3m, 6m, 1y)
        current_user: Authenticated user
        
    Returns:
        Vehicle classification analytics
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        classifications = await analytics_service.analyze_vehicle_classifications(
            center_id=center_id,
            time_period=time_period,
            user_role=current_user.role
        )

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
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Analyze test failure patterns and common issues.
    
    Args:
        center_id: Optional center ID for filtering
        vehicle_type: Optional vehicle type filter
        time_period: Analysis time period
        current_user: Authenticated user
        
    Returns:
        Test failure pattern analysis
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        failure_analysis = await analytics_service.analyze_failure_patterns(
            center_id=center_id,
            vehicle_type=vehicle_type,
            time_period=time_period,
            user_role=current_user.role
        )

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
    metric_type: str,
    dimension: str,
    time_period: str = "1m",
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Get detailed performance metrics and KPIs.
    
    Args:
        metric_type: Type of metric to analyze
        dimension: Analysis dimension
        time_period: Analysis time period
        current_user: Authenticated user
        
    Returns:
        Performance metrics analysis
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        metrics = await analytics_service.get_performance_metrics(
            metric_type=metric_type,
            dimension=dimension,
            time_period=time_period,
            user_role=current_user.role
        )

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
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> TrendAnalysis:
    """Generate trend forecasts for specified metrics.
    
    Args:
        metric: Metric to forecast
        forecast_period: Forecast period in days
        current_user: Authenticated user
        
    Returns:
        Trend forecast analysis
        
    Raises:
        HTTPException: If forecast fails
    """
    try:
        forecast = await analytics_service.generate_forecast(
            metric=metric,
            forecast_period=forecast_period,
            user_role=current_user.role
        )

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
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ANALYTICS))
) -> AnalyticsResponse:
    """Generate comprehensive analytics summary report.
    
    Args:
        report_type: Type of analytics report
        time_period: Analysis time period
        current_user: Authenticated user
        
    Returns:
        Analytics summary report
        
    Raises:
        HTTPException: If report generation fails
    """
    try:
        summary = await analytics_service.generate_analytics_summary(
            report_type=report_type,
            time_period=time_period,
            user_role=current_user.role
        )

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