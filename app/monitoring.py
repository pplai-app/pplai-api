"""
Google Cloud Monitoring integration for metrics
Exports metrics to Cloud Monitoring for Grafana visualization
"""
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Try to import Google Cloud Monitoring
try:
    from google.cloud import monitoring_v3
    from google.cloud.monitoring_v3 import MetricServiceClient
    from google.api import metric_pb2 as ga_metric
    from google.api import monitored_resource_pb2
    GCP_MONITORING_AVAILABLE = True
except ImportError:
    GCP_MONITORING_AVAILABLE = False
    monitoring_v3 = None

USE_GCP_MONITORING = os.getenv('USE_GCP_MONITORING', 'true').lower() == 'true'
PROJECT_ID = os.getenv('GCP_PROJECT_ID')
METRIC_PREFIX = 'custom.googleapis.com/pplai'


class CloudMonitoringExporter:
    """Export metrics to Google Cloud Monitoring"""
    
    def __init__(self):
        self.client: Optional[MetricServiceClient] = None
        self.project_name: Optional[str] = None
        
        if USE_GCP_MONITORING and GCP_MONITORING_AVAILABLE and PROJECT_ID:
            try:
                self.client = MetricServiceClient()
                self.project_name = f"projects/{PROJECT_ID}"
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to initialize Cloud Monitoring: {e}")
    
    def write_time_series(
        self,
        metric_type: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """Write a time series data point to Cloud Monitoring"""
        if not self.client or not self.project_name:
            return
        
        try:
            series = monitoring_v3.TimeSeries()
            series.metric.type = f"{METRIC_PREFIX}/{metric_type}"
            
            # Set resource type (Cloud Run)
            series.resource.type = "cloud_run_revision"
            series.resource.labels["project_id"] = PROJECT_ID
            series.resource.labels["service_name"] = os.getenv('GCP_SERVICE_NAME', 'pplai-api')
            series.resource.labels["revision_name"] = os.getenv('GCP_REVISION_NAME', 'default')
            series.resource.labels["location"] = os.getenv('GCP_REGION', 'us-central1')
            
            # Set metric labels
            if labels:
                for key, value in labels.items():
                    series.metric.labels[key] = str(value)
            
            # Set data point
            now = datetime.utcnow()
            point = monitoring_v3.Point()
            point.value.double_value = float(value)
            point.interval.end_time.seconds = int(now.timestamp())
            point.interval.end_time.nanos = int((now.timestamp() % 1) * 1e9)
            series.points = [point]
            
            # Write to Cloud Monitoring
            self.client.create_time_series(
                name=self.project_name,
                time_series=[series]
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to write metric to Cloud Monitoring: {e}")
    
    def record_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float
    ):
        """Record API request metric"""
        labels = {
            'method': method,
            'path': path,
            'status_code': str(status_code)
        }
        self.write_time_series('api/request_duration', duration_ms, labels)
        self.write_time_series('api/request_count', 1, labels)
    
    def record_db_query(
        self,
        operation: str,
        table: str,
        duration_ms: float
    ):
        """Record database query metric"""
        labels = {
            'operation': operation,
            'table': table
        }
        self.write_time_series('db/query_duration', duration_ms, labels)
        self.write_time_series('db/query_count', 1, labels)
    
    def record_business_event(
        self,
        event_type: str
    ):
        """Record business event metric"""
        labels = {'event_type': event_type}
        self.write_time_series('business/event_count', 1, labels)


# Global monitoring exporter instance
monitoring = CloudMonitoringExporter() if (USE_GCP_MONITORING and GCP_MONITORING_AVAILABLE) else None

