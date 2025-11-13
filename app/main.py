from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv
import logging

from app.database import engine, Base
from app.routers import auth, profile, events, contacts, followups, export, tags, admin
from app.middleware import MetricsMiddleware
from app.logging_config import metrics

logger = logging.getLogger(__name__)

# Load environment-specific .env file
env = os.getenv('ENVIRONMENT', 'development')
env_file = f'.env.{env}'

# Try to load environment-specific file, fallback to .env
if os.path.exists(env_file):
    load_dotenv(env_file)
    logger.info(f"Loaded environment file: {env_file}")
else:
    # Fallback to default .env file
    load_dotenv()
    logger.warning(f"{env_file} not found, using .env (if exists)")

# Note: Database tables are created via migrations, not here
# Base.metadata.create_all() is removed to avoid connection issues at startup
# Migrations are run in CI/CD before deployment

app = FastAPI(
    title="pplai.app API",
    description="Backend API for pplai.app networking app",
    version="1.0.0"
)

# CORS middleware - MUST be added before routes
# Get allowed origins from environment or use defaults
frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
cors_origins = os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else [
    frontend_url,
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
# Filter out empty strings
cors_origins = [origin.strip() for origin in cors_origins if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Metrics middleware - logs all API requests with timing
app.add_middleware(MetricsMiddleware)

# Include routers with /api prefix
app.include_router(auth.router, prefix="/api/auth")
app.include_router(profile.router, prefix="/api/profile")
app.include_router(events.router, prefix="/api/events")
app.include_router(contacts.router, prefix="/api/contacts")
app.include_router(followups.router, prefix="/api/followups")
app.include_router(export.router, prefix="/api/export")
app.include_router(tags.router, prefix="/api/tags")
app.include_router(admin.router, prefix="/api/admins")

# Serve local uploads if using local storage
if os.path.exists('uploads'):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "service": "pplai.app API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    from sqlalchemy import text
    try:
        # Test database connection with timeout
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        db_status = f"disconnected: {str(e)[:100]}"
    
    return {
        "status": "ok",
        "service": "pplai.app API",
        "database": db_status,
        "environment": os.getenv('ENVIRONMENT', 'development')
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler - never expose sensitive details"""
    import logging
    import traceback
    from fastapi.middleware.cors import CORSMiddleware
    
    # Log full error details server-side only (not exposed to client)
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Report to GCP Error Reporting
    from app.logging_config import error_client
    if error_client:
        try:
            error_client.report_exception()
        except:
            pass
    
    # Return generic error message to client with CORS headers
    response = JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )
    
    # Add CORS headers to error response
    origin = request.headers.get("origin")
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
    cors_origins = os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else [
        frontend_url,
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cors_origins = [o.strip() for o in cors_origins if o.strip()]
    
    if origin and origin in cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

