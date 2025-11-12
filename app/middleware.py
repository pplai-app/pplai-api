"""
Middleware for request/response logging and metrics
"""
import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging_config import metrics

# Import monitoring (may be None if not configured)
try:
    from app.monitoring import monitoring
except ImportError:
    monitoring = None

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to log API requests and responses with timing"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip logging for health checks and static files
        if request.url.path in ['/api/health', '/docs', '/openapi.json', '/redoc']:
            return await call_next(request)
        
        # Start timer
        start_time = time.time()
        
        # Extract user info if available (from token)
        user_id = None
        try:
            # Try to extract user from request state (set by auth dependency)
            if hasattr(request.state, 'user_id'):
                user_id = str(request.state.user_id)
        except Exception:
            pass
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log metrics
            metrics.log_api_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=user_id,
                query_params=str(request.query_params) if request.query_params else None
            )
            
            # Export to Cloud Monitoring for Grafana
            if monitoring:
                monitoring.record_api_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms
                )
            
            # Add timing header
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            return response
            
        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.time() - start_time) * 1000
            
            # Log error metrics
            metrics.log_api_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                user_id=user_id,
                error=str(e)
            )
            
            raise


class DatabaseMetricsMiddleware:
    """Context manager for database query timing"""
    
    def __init__(self, operation: str, table: str, user_id: str = None):
        self.operation = operation
        self.table = table
        self.user_id = user_id
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            metrics.log_db_query(
                operation=self.operation,
                table=self.table,
                duration_ms=duration_ms,
                user_id=self.user_id,
                error=str(exc_val) if exc_val else None
            )
            
            # Export to Cloud Monitoring for Grafana
            if monitoring:
                monitoring.record_db_query(
                    operation=self.operation,
                    table=self.table,
                    duration_ms=duration_ms
                )

