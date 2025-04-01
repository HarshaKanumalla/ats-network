import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import psutil
import asyncio
from bson import ObjectId

from ...core.exceptions import MonitoringError
from ...database import get_database
from ...config import get_settings
from ...services.cache import cache_service
from ...services.notification import notification_service

logger = logging.getLogger(__name__)
settings = get_settings()

class MetricsService:
    """Service for system-wide metrics collection and monitoring."""
    
    def __init__(self):
        """Initialize metrics service with monitoring configuration."""
        self.db = None
        self.metrics_buffer = {}
        
        # Monitoring thresholds
        self.thresholds = {
            'cpu_usage': 80.0,          # percentage
            'memory_usage': 85.0,       # percentage
            'disk_usage': 90.0,         # percentage
            'response_time': 1000,      # milliseconds
            'error_rate': 5.0,          # percentage
            'connection_limit': 1000    # concurrent connections
        }
        
        # Collection intervals (seconds)
        self.intervals = {
            'system_metrics': 60,
            'application_metrics': 30,
            'performance_metrics': 300,
            'test_metrics': 10
        }
        
        # Metrics retention
        self.retention_periods = {
            'system_metrics': timedelta(days=7),
            'performance_metrics': timedelta(days=30),
            'test_metrics': timedelta(days=90)
        }
        
        logger.info("Metrics service initialized")

    async def start_monitoring(self) -> None:
        """Start all monitoring tasks."""
        try:
            monitoring_tasks = [
                asyncio.create_task(self._collect_system_metrics()),
                asyncio.create_task(self._collect_application_metrics()),
                asyncio.create_task(self._collect_performance_metrics()),
                asyncio.create_task(self._monitor_test_sessions()),
                asyncio.create_task(self._cleanup_old_metrics())
            ]
            await asyncio.gather(*monitoring_tasks)
        except Exception as e:
            logger.error(f"Monitoring startup error: {str(e)}")
            raise MonitoringError("Failed to start monitoring")

    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status."""
        try:
            # Collect current metrics
            cpu_usage = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get application metrics
            app_metrics = await self._get_application_metrics()
            
            # Check component status
            database_status = await self._check_database_health()
            cache_status = await self._check_cache_health()
            storage_status = await self._check_storage_health()
            
            health_status = {
                'timestamp': datetime.utcnow(),
                'status': 'healthy',  # Will be updated based on checks
                'metrics': {
                    'system': {
                        'cpu_usage': cpu_usage,
                        'memory_usage': memory.percent,
                        'disk_usage': disk.percent,
                        'load_average': psutil.getloadavg()
                    },
                    'application': app_metrics
                },
                'components': {
                    'database': database_status,
                    'cache': cache_status,
                    'storage': storage_status
                }
            }
            
            # Determine overall status
            if any(not status['healthy'] for status in health_status['components'].values()):
                health_status['status'] = 'degraded'
                
            if (cpu_usage > self.thresholds['cpu_usage'] or 
                memory.percent > self.thresholds['memory_usage'] or
                disk.percent > self.thresholds['disk_usage']):
                health_status['status'] = 'warning'
                
            return health_status
            
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            raise MonitoringError("Failed to check system health")

    async def collect_center_metrics(
        self,
        center_id: str
    ) -> Dict[str, Any]:
        """Collect metrics for specific ATS center."""
        try:
            db = await get_database()
            
            # Get recent test sessions
            recent_tests = await db.testSessions.find({
                'centerId': ObjectId(center_id),
                'testDate': {
                    '$gte': datetime.utcnow() - timedelta(days=7)
                }
            }).to_list(None)
            
            # Calculate metrics
            total_tests = len(recent_tests)
            completed_tests = len([t for t in recent_tests if t['status'] == 'completed'])
            failed_tests = len([t for t in recent_tests if t['status'] == 'failed'])
            
            average_duration = 0
            if completed_tests > 0:
                durations = [
                    (t['endTime'] - t['startTime']).total_seconds()
                    for t in recent_tests
                    if t.get('endTime') and t.get('startTime')
                ]
                average_duration = sum(durations) / len(durations)
            
            return {
                'timestamp': datetime.utcnow(),
                'center_id': center_id,
                'metrics': {
                    'total_tests': total_tests,
                    'completed_tests': completed_tests,
                    'failed_tests': failed_tests,
                    'success_rate': (completed_tests / total_tests * 100) if total_tests > 0 else 0,
                    'average_duration': average_duration,
                    'active_sessions': len([t for t in recent_tests if t['status'] == 'in_progress'])
                }
            }
            
        except Exception as e:
            logger.error(f"Center metrics collection error: {str(e)}")
            raise MonitoringError("Failed to collect center metrics")

    async def _collect_system_metrics(self) -> None:
        """Collect system-level metrics periodically."""
        while True:
            try:
                metrics = {
                    'timestamp': datetime.utcnow(),
                    'cpu': {
                        'usage': psutil.cpu_percent(interval=1),
                        'cores': psutil.cpu_count(),
                        'load': psutil.getloadavg()
                    },
                    'memory': {
                        'total': psutil.virtual_memory().total,
                        'available': psutil.virtual_memory().available,
                        'used': psutil.virtual_memory().used,
                        'percent': psutil.virtual_memory().percent
                    },
                    'disk': {
                        'total': psutil.disk_usage('/').total,
                        'used': psutil.disk_usage('/').used,
                        'free': psutil.disk_usage('/').free,
                        'percent': psutil.disk_usage('/').percent
                    },
                    'network': {
                        'connections': len(psutil.net_connections()),
                        'io_counters': psutil.net_io_counters()._asdict()
                    }
                }
                
                # Store metrics
                await self._store_metrics('system', metrics)
                
                # Check thresholds and alert if needed
                await self._check_thresholds(metrics)
                
                await asyncio.sleep(self.intervals['system_metrics'])
                
            except Exception as e:
                logger.error(f"System metrics collection error: {str(e)}")
                await asyncio.sleep(10)  # Retry after delay

    async def _collect_application_metrics(self) -> None:
        """Collect application-specific metrics."""
        while True:
            try:
                db = await get_database()
                
                metrics = {
                    'timestamp': datetime.utcnow(),
                    'active_sessions': await db.testSessions.count_documents({
                        'status': 'in_progress'
                    }),
                    'pending_approvals': await db.users.count_documents({
                        'status': 'pending'
                    }),
                    'active_centers': await db.centers.count_documents({
                        'status': 'active'
                    })
                }
                
                # Get cache statistics
                cache_info = await cache_service.get_stats()
                metrics['cache'] = cache_info
                
                # Store metrics
                await self._store_metrics('application', metrics)
                
                await asyncio.sleep(self.intervals['application_metrics'])
                
            except Exception as e:
                logger.error(f"Application metrics collection error: {str(e)}")
                await asyncio.sleep(10)

    async def _check_thresholds(self, metrics: Dict[str, Any]) -> None:
        """Check metrics against thresholds and send alerts."""
        alerts = []
        
        if metrics['cpu']['usage'] > self.thresholds['cpu_usage']:
            alerts.append({
                'type': 'high_cpu_usage',
                'value': metrics['cpu']['usage'],
                'threshold': self.thresholds['cpu_usage']
            })
            
        if metrics['memory']['percent'] > self.thresholds['memory_usage']:
            alerts.append({
                'type': 'high_memory_usage',
                'value': metrics['memory']['percent'],
                'threshold': self.thresholds['memory_usage']
            })
            
        if metrics['disk']['percent'] > self.thresholds['disk_usage']:
            alerts.append({
                'type': 'high_disk_usage',
                'value': metrics['disk']['percent'],
                'threshold': self.thresholds['disk_usage']
            })
            
        for alert in alerts:
            await notification_service.send_system_alert(
                alert_type=alert['type'],
                details={
                    'current_value': alert['value'],
                    'threshold': alert['threshold'],
                    'timestamp': datetime.utcnow()
                }
            )

    async def _store_metrics(
        self,
        metric_type: str,
        metrics: Dict[str, Any]
    ) -> None:
        """Store collected metrics in database."""
        try:
            db = await get_database()
            
            await db.metrics.insert_one({
                'type': metric_type,
                'data': metrics,
                'timestamp': metrics['timestamp']
            })
            
            # Update cache for quick access
            cache_key = f"metrics:{metric_type}:latest"
            await cache_service.set(cache_key, metrics, ttl=300)
            
        except Exception as e:
            logger.error(f"Metrics storage error: {str(e)}")

    async def _cleanup_old_metrics(self) -> None:
        """Clean up old metrics data periodically."""
        while True:
            try:
                db = await get_database()
                
                for metric_type, retention in self.retention_periods.items():
                    cutoff_date = datetime.utcnow() - retention
                    
                    await db.metrics.delete_many({
                        'type': metric_type,
                        'timestamp': {'$lt': cutoff_date}
                    })
                
                await asyncio.sleep(86400)  # Run daily
                
            except Exception as e:
                logger.error(f"Metrics cleanup error: {str(e)}")
                await asyncio.sleep(3600)  # Retry after an hour

# Initialize metrics service
metrics_service = MetricsService()