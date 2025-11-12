"""
Logging configuration for pplai.app API
Provides structured logging with Google Cloud Logging integration
"""
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import json

# Try to import Google Cloud Logging
try:
    import google.cloud.logging
    from google.cloud.logging.handlers import CloudLoggingHandler
    from google.cloud.logging.resource import Resource
    GCP_LOGGING_AVAILABLE = True
except ImportError:
    GCP_LOGGING_AVAILABLE = False
    CloudLoggingHandler = None

# Try to import Google Cloud Error Reporting
try:
    from google.cloud import error_reporting
    GCP_ERROR_REPORTING_AVAILABLE = True
except ImportError:
    GCP_ERROR_REPORTING_AVAILABLE = False
    error_reporting = None

# Configure logging based on environment
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO' if ENVIRONMENT == 'production' else 'DEBUG')
USE_GCP_LOGGING = os.getenv('USE_GCP_LOGGING', 'true' if ENVIRONMENT in ['beta', 'production'] else 'false').lower() == 'true'

# Initialize GCP Error Reporting client
error_client: Optional[Any] = None
if GCP_ERROR_REPORTING_AVAILABLE and USE_GCP_LOGGING:
    try:
        error_client = error_reporting.Client()
    except Exception as e:
        print(f"Warning: Failed to initialize GCP Error Reporting: {e}")

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL.upper()))

# Remove existing handlers
root_logger.handlers = []

# Console handler (always enabled)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(getattr(logging, LOG_LEVEL.upper()))
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# File handler for local development
if ENVIRONMENT == 'development':
    if not os.path.exists('logs'):
        os.makedirs('logs')
    file_handler = logging.FileHandler(f'logs/pplai_{ENVIRONMENT}.log', encoding='utf-8')
    file_handler.setLevel(getattr(logging, LOG_LEVEL.upper()))
    file_handler.setFormatter(console_formatter)
    root_logger.addHandler(file_handler)

# Google Cloud Logging handler (for beta/production)
if USE_GCP_LOGGING and GCP_LOGGING_AVAILABLE:
    try:
        client = google.cloud.logging.Client()
        # Create resource descriptor for GCP
        resource = Resource(
            type="cloud_run_revision",  # or "gce_instance", "k8s_container", etc.
            labels={
                "service_name": os.getenv('GCP_SERVICE_NAME', 'pplai-api'),
                "revision_name": os.getenv('GCP_REVISION_NAME', 'default'),
            }
        )
        cloud_handler = CloudLoggingHandler(client, resource=resource)
        cloud_handler.setLevel(logging.INFO)  # Only send INFO and above to Cloud Logging
        root_logger.addHandler(cloud_handler)
        print("Google Cloud Logging enabled")
    except Exception as e:
        print(f"Warning: Failed to initialize Google Cloud Logging: {e}. Using local logging only.")

# Suppress noisy loggers
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('google').setLevel(logging.WARNING)  # Reduce GCP SDK noise


class MetricsLogger:
    """Structured metrics logger for API and database operations"""
    
    def __init__(self, logger_name: str = 'pplai.metrics'):
        self.logger = logging.getLogger(logger_name)
    
    def log_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: str = None,
        **kwargs
    ):
        """Log API request with metrics"""
        metrics = {
            'type': 'api_request',
            'method': method,
            'path': path,
            'status_code': status_code,
            'duration_ms': round(duration_ms, 2),
            'timestamp': datetime.utcnow().isoformat(),
        }
        if user_id:
            metrics['user_id'] = str(user_id)
        metrics.update(kwargs)
        
        # Log level based on status code
        if status_code >= 500:
            self.logger.error(f"API Request: {json.dumps(metrics)}")
            # Report to GCP Error Reporting
            if error_client:
                try:
                    error_client.report(f"API Error {status_code}: {method} {path}", user_id=user_id)
                except:
                    pass
        elif status_code >= 400:
            self.logger.warning(f"API Request: {json.dumps(metrics)}")
        else:
            self.logger.info(f"API Request: {json.dumps(metrics)}")
    
    def log_db_query(
        self,
        operation: str,
        table: str,
        duration_ms: float,
        rows_affected: int = None,
        user_id: str = None,
        **kwargs
    ):
        """Log database query with metrics"""
        metrics = {
            'type': 'db_query',
            'operation': operation,
            'table': table,
            'duration_ms': round(duration_ms, 2),
            'timestamp': datetime.utcnow().isoformat(),
        }
        if rows_affected is not None:
            metrics['rows_affected'] = rows_affected
        if user_id:
            metrics['user_id'] = str(user_id)
        metrics.update(kwargs)
        
        # Log slow queries as warnings
        if duration_ms > 1000:
            self.logger.warning(f"Slow DB Query: {json.dumps(metrics)}")
        else:
            self.logger.debug(f"DB Query: {json.dumps(metrics)}")
    
    def log_business_event(
        self,
        event_type: str,
        user_id: str = None,
        **kwargs
    ):
        """Log business events (user actions, etc.)"""
        metrics = {
            'type': 'business_event',
            'event_type': event_type,
            'timestamp': datetime.utcnow().isoformat(),
        }
        if user_id:
            metrics['user_id'] = str(user_id)
        metrics.update(kwargs)
        
        self.logger.info(f"Business Event: {json.dumps(metrics)}")
    
    def log_error(
        self,
        error_type: str,
        error_message: str,
        user_id: str = None,
        exc_info: bool = False,
        **kwargs
    ):
        """Log errors with context and report to GCP Error Reporting"""
        metrics = {
            'type': 'error',
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': datetime.utcnow().isoformat(),
        }
        if user_id:
            metrics['user_id'] = str(user_id)
        metrics.update(kwargs)
        
        self.logger.error(f"Error: {json.dumps(metrics)}", exc_info=exc_info)
        
        # Report to GCP Error Reporting
        if error_client:
            try:
                error_client.report(
                    f"{error_type}: {error_message}",
                    user=user_id,
                    **kwargs
                )
            except Exception as e:
                # Don't fail if error reporting fails
                pass


# Global metrics logger instance
metrics = MetricsLogger()
