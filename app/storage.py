import uuid
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

# Try to import Google Cloud Storage
try:
    from google.cloud import storage as gcs_storage
    from google.cloud.exceptions import NotFound, GoogleCloudError
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    gcs_storage = None

# Load environment-specific .env file
env = os.getenv('ENVIRONMENT', 'development')
env_file = f'.env.{env}'
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

# Check if GCS is configured (bucket name is required)
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
USE_GCS = bool(GCS_BUCKET_NAME and GCS_AVAILABLE)

# Google Cloud Storage client (uses Application Default Credentials or service account)
gcs_client: Optional[gcs_storage.Client] = None
if USE_GCS:
    try:
        # Initialize GCS client - uses Application Default Credentials
        # In GCP, this automatically uses the service account
        # Locally, use: gcloud auth application-default login
        gcs_client = gcs_storage.Client()
        # Test connection by checking if bucket exists
        bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        if not bucket.exists():
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"GCS bucket {GCS_BUCKET_NAME} does not exist. Creating...")
            try:
                bucket.create()
                logger.info(f"Created GCS bucket: {GCS_BUCKET_NAME}")
            except Exception as e:
                logger.error(f"Failed to create GCS bucket: {e}")
                USE_GCS = False
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize GCS client: {e}. Falling back to local storage.", exc_info=True)
        USE_GCS = False
        gcs_client = None

# Local storage fallback for development
LOCAL_STORAGE_DIR = Path('uploads')
LOCAL_STORAGE_DIR.mkdir(exist_ok=True)
LOCAL_STORAGE_URL = os.getenv('LOCAL_STORAGE_URL', 'http://localhost:8000/uploads')


def upload_file_to_s3(file_content: bytes, file_name: str, content_type: str, folder: str = 'uploads') -> str:
    """
    Upload a file to Google Cloud Storage (or local storage as fallback) and return the public URL
    
    Args:
        file_content: File content as bytes
        file_name: Original file name
        content_type: MIME type of the file
        folder: GCS folder path (e.g., 'profiles', 'contacts', 'media')
    
    Returns:
        Public URL of the uploaded file
    """
    # Generate unique file name
    file_extension = os.path.splitext(file_name)[1]
    unique_file_name = f"{folder}/{uuid.uuid4()}{file_extension}"
    
    # Try GCS first if configured
    if USE_GCS and gcs_client:
        try:
            bucket = gcs_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(unique_file_name)
            
            # Upload file with content type
            blob.upload_from_string(
                file_content,
                content_type=content_type
            )
            
            # Make blob publicly readable
            blob.make_public()
            
            # Return public URL
            return blob.public_url
        except (NotFound, GoogleCloudError, Exception) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("GCS upload failed, falling back to local storage", exc_info=True)
            # Fall through to local storage
    
    # Fallback to local storage
    folder_path = LOCAL_STORAGE_DIR / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    
    file_path = folder_path / f"{uuid.uuid4()}{file_extension}"
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    # Return local URL
    return f"{LOCAL_STORAGE_URL}/{folder}/{file_path.name}"


def delete_file_from_s3(file_url: str) -> bool:
    """
    Delete a file from Google Cloud Storage or local storage
    
    Args:
        file_url: Public URL of the file to delete
    
    Returns:
        True if successful, False otherwise
    """
    # Check if it's a local storage URL
    if LOCAL_STORAGE_URL in file_url:
        try:
            # Extract file path from URL
            url_parts = file_url.replace(LOCAL_STORAGE_URL + '/', '').split('/')
            if len(url_parts) >= 2:
                file_path = LOCAL_STORAGE_DIR / '/'.join(url_parts)
                if file_path.exists():
                    file_path.unlink()
                    return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Error deleting local file", exc_info=True)
        return False
    
    # Try GCS deletion if configured
    if USE_GCS and gcs_client:
        try:
            # Extract blob name from GCS URL
            # URL format: https://storage.googleapis.com/bucket-name/folder/filename
            # or: https://bucket-name.storage.googleapis.com/folder/filename
            if 'storage.googleapis.com' in file_url:
                # Extract path after bucket name
                if f'/{GCS_BUCKET_NAME}/' in file_url:
                    blob_name = file_url.split(f'/{GCS_BUCKET_NAME}/')[1]
                else:
                    # Try alternative format
                    parts = file_url.split('/')
                    bucket_idx = -1
                    for i, part in enumerate(parts):
                        if GCS_BUCKET_NAME in part:
                            bucket_idx = i
                            break
                    if bucket_idx >= 0 and bucket_idx + 1 < len(parts):
                        blob_name = '/'.join(parts[bucket_idx + 1:])
                    else:
                        return False
                
                bucket = gcs_client.bucket(GCS_BUCKET_NAME)
                blob = bucket.blob(blob_name)
                blob.delete()
                return True
        except (NotFound, GoogleCloudError, Exception) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Error deleting from GCS", exc_info=True)
            return False
    
    return False


def get_file_type(content_type: str) -> str:
    """
    Determine file type from MIME type
    
    Args:
        content_type: MIME type
    
    Returns:
        File type: 'image', 'audio', or 'document'
    """
    if content_type.startswith('image/'):
        return 'image'
    elif content_type.startswith('audio/'):
        return 'audio'
    else:
        return 'document'

