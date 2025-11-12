# pplai.app - Backend API

FastAPI-based backend for the pplai.app networking application.

## Features

- User authentication (OAuth & Email/Password)
- Profile management
- Event management
- Contact management with tags
- QR code generation (URL & vCard)
- Media attachments
- Follow-ups
- Admin panel
- Export (PDF/CSV)
- Comprehensive logging and metrics

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy
- **Authentication**: JWT
- **Storage**: Google Cloud Storage (with local fallback)
- **Cache**: Redis (optional, caching disabled if not configured)
- **QR Codes**: qrcode[pil]

## Setup

### Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+ (optional, for caching - improves performance for frequently accessed profiles)
- AWS S3 credentials (optional, local storage fallback available)

### Installation

1. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp env.example .env.development
   # Edit .env.development with your settings
   ```

4. **Set up database:**
   ```bash
   # Create database
   createdb pplai_dev
   
   # Run migrations
   psql -d pplai_dev -f migrations/schema.sql
   psql -d pplai_dev -f migrations/add_password_to_users.sql
   psql -d pplai_dev -f migrations/add_user_id_to_tags.sql
   psql -d pplai_dev -f migrations/add_is_hidden_to_tags.sql
   psql -d pplai_dev -f migrations/add_location_to_contacts.sql
   psql -d pplai_dev -f migrations/add_is_admin_to_users.sql
   psql -d pplai_dev -f migrations/add_user_indexes.sql
   ```

5. **Set up Redis (optional but recommended):**
   ```bash
   # Install Redis (macOS)
   brew install redis
   
   # Start Redis
   redis-server
   
   # Or use Docker
   docker run -d -p 6379:6379 redis:7-alpine
   ```
   
   Configure Redis URL in `.env.development`:
   ```bash
   REDIS_URL=redis://localhost:6379/0
   ```
   
   **Note**: The application will work without Redis, but caching will be disabled. Redis significantly improves performance for frequently accessed profiles (especially public profiles accessed via QR codes).

6. **Create admin user:**
   ```bash
   # First, sign up a user through the app
   # Then promote to admin:
   python create_admin.py user@example.com
   ```

7. **Run server:**
   ```bash
   # Development
   export ENVIRONMENT=development
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   
   # Or use the startup script:
   ./START_SERVER_DEV.sh
   ```

## Environment Variables

See `env.example` for all available environment variables.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `JWT_SECRET_KEY`: Secret for JWT token signing
- `FRONTEND_URL`: Frontend URL for CORS
- `REDIS_URL`: Redis connection URL (optional, e.g., `redis://localhost:6379/0`)
- `AWS_ACCESS_KEY_ID`: AWS S3 access key (optional)
- `AWS_SECRET_ACCESS_KEY`: AWS S3 secret key (optional)
- `AWS_S3_BUCKET`: S3 bucket name (optional)
- `ENVIRONMENT`: Environment name (development/beta/production)

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── auth.py              # Authentication utilities
│   ├── storage.py           # File storage (S3/local)
│   ├── cache.py             # Redis caching utilities
│   ├── middleware.py        # Request middleware
│   ├── logging_config.py    # Logging setup
│   └── routers/             # API routes
│       ├── auth.py
│       ├── profile.py
│       ├── events.py
│       ├── contacts.py
│       ├── tags.py
│       ├── followups.py
│       ├── export.py
│       └── admin.py
├── migrations/              # SQL migration scripts
├── create_admin.py         # Admin user creation script
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Development

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Format code
black app/

# Lint
flake8 app/
```

## Caching

The application uses Redis for server-side caching to improve performance:

- **Public Profiles**: Cached for 1 hour (frequently accessed via QR codes)
- **User Profiles**: Cached for 30 minutes
- **QR Codes**: Cached for 2 hours (they don't change often)

Cache is automatically invalidated when profiles are updated. If Redis is not configured, the application will work normally but without caching benefits.

## Production Deployment

1. Set `ENVIRONMENT=production` in your environment
2. Configure production database URL
3. Set up Redis for caching (highly recommended for performance)
4. Set up AWS S3 for file storage
5. Use a production WSGI server (e.g., Gunicorn with Uvicorn workers)
6. Set up proper logging and monitoring

## License

Proprietary - All rights reserved
