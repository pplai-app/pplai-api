from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import time
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment-specific .env file
env = os.getenv('ENVIRONMENT', 'development')
env_file = f'.env.{env}'
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pplai')}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_timeout=10,  # Wait max 10 seconds for connection from pool
    connect_args={
        "connect_timeout": 10,  # Increased to 10 seconds
        "application_name": "meet_ai"
    },
    echo=os.getenv('ENVIRONMENT', 'development') == 'development'  # Only echo SQL in development
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Database query timing - only log in development
@event.listens_for(engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())
    # Only log in development mode
    if os.getenv('ENVIRONMENT', 'development') == 'development':
        logger.debug(f"Query: {statement[:100]}...")

@event.listens_for(engine, "after_cursor_execute")
def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if 'query_start_time' in conn.info and conn.info['query_start_time']:
        total = time.time() - conn.info['query_start_time'].pop(-1)
        # Only log in development mode
        if os.getenv('ENVIRONMENT', 'development') == 'development':
            logger.debug(f"Query time: {total*1000:.2f}ms")


def get_db():
    """Dependency for getting database session"""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        # Test connection before yielding (quick ping)
        try:
            db.execute(text("SELECT 1"))
        except Exception as conn_error:
            logger.error(f"Database connection test failed: {conn_error}", exc_info=True)
            try:
                db.rollback()
                db.close()
            except:
                pass
            # Recreate session
            db = SessionLocal()
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        raise
    finally:
        try:
            db.close()
        except:
            pass

