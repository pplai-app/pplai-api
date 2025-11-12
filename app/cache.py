"""
Redis cache utility for caching profile data and other frequently accessed resources.
"""
import json
import logging
from typing import Optional, Any
import os
from functools import wraps

logger = logging.getLogger(__name__)

# Try to import redis, but make it optional
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not installed. Caching will be disabled. Install with: pip install redis")

# Redis connection pool (singleton)
_redis_client: Optional[Any] = None


def get_redis_client():
    """Get or create Redis client"""
    global _redis_client
    
    if not REDIS_AVAILABLE:
        return None
    
    if _redis_client is None:
        try:
            # Check if Redis is explicitly disabled
            redis_enabled = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'
            if not redis_enabled:
                logger.info("Redis caching is disabled via REDIS_ENABLED=false")
                return None
            
            redis_url = os.getenv('REDIS_URL')
            # Parse Redis URL if provided
            if redis_url and redis_url.startswith('redis://'):
                # Extract host, port, db from URL
                parts = redis_url.replace('redis://', '').split('/')
                host_port = parts[0].split(':')
                host = host_port[0] if host_port else 'localhost'
                port = int(host_port[1]) if len(host_port) > 1 else 6379
                db = int(parts[1]) if len(parts) > 1 else 0
            else:
                # Use individual settings or defaults
                host = os.getenv('REDIS_HOST', 'localhost')
                port = int(os.getenv('REDIS_PORT', 6379))
                db = int(os.getenv('REDIS_DB', 0))
            
            # Create Redis client with connection pool
            _redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,  # Automatically decode responses to strings
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            _redis_client.ping()
            logger.info(f"Redis connected: {host}:{port}/{db}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching disabled.")
            _redis_client = None
    
    return _redis_client


def cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate cache key from prefix and arguments"""
    key_parts = [prefix]
    if args:
        key_parts.extend(str(arg) for arg in args)
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        key_parts.extend(f"{k}:{v}" for k, v in sorted_kwargs)
    return ":".join(key_parts)


def get_cached(key: str) -> Optional[Any]:
    """Get value from cache"""
    client = get_redis_client()
    if not client:
        return None
    
    try:
        value = client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        logger.warning(f"Error getting from cache: {e}")
    return None


def set_cached(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set value in cache with TTL (time to live in seconds)"""
    client = get_redis_client()
    if not client:
        return False
    
    try:
        serialized = json.dumps(value, default=str)  # default=str handles datetime, UUID, etc.
        client.setex(key, ttl, serialized)
        return True
    except Exception as e:
        logger.warning(f"Error setting cache: {e}")
    return False


def delete_cached(key: str) -> bool:
    """Delete value from cache"""
    client = get_redis_client()
    if not client:
        return False
    
    try:
        client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Error deleting from cache: {e}")
    return False


def invalidate_pattern(pattern: str) -> int:
    """Invalidate all keys matching a pattern"""
    client = get_redis_client()
    if not client:
        return 0
    
    try:
        keys = client.keys(pattern)
        if keys:
            return client.delete(*keys)
    except Exception as e:
        logger.warning(f"Error invalidating cache pattern: {e}")
    return 0


def cached(ttl: int = 3600, key_prefix: Optional[str] = None):
    """
    Decorator to cache function results
    
    Args:
        ttl: Time to live in seconds (default: 1 hour)
        key_prefix: Prefix for cache key (default: function name)
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}.{func.__name__}"
            cache_key_str = cache_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_value = get_cached(cache_key_str)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key_str}")
                return cached_value
            
            # Cache miss - call function
            logger.debug(f"Cache miss: {cache_key_str}")
            result = await func(*args, **kwargs)
            
            # Store in cache
            set_cached(cache_key_str, result, ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}.{func.__name__}"
            cache_key_str = cache_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_value = get_cached(cache_key_str)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key_str}")
                return cached_value
            
            # Cache miss - call function
            logger.debug(f"Cache miss: {cache_key_str}")
            result = func(*args, **kwargs)
            
            # Store in cache
            set_cached(cache_key_str, result, ttl)
            
            return result
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

