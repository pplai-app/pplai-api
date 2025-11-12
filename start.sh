#!/bin/bash
# Start script for pplai.app Backend

export ENVIRONMENT=${ENVIRONMENT:-development}

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload

