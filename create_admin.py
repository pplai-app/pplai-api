#!/usr/bin/env python3
"""
Script to create or promote a user to admin
Usage: python create_admin.py <email>
"""
import sys
import os
from dotenv import load_dotenv

# Load environment
env = os.getenv('ENVIRONMENT', 'development')
env_file = f'.env.{env}'
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

from app.database import SessionLocal
from app.models import User

def create_admin(email: str):
    """Create or promote a user to admin"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ User with email {email} not found.")
            print("   Please create the user first through normal signup, then run this script again.")
            return False
        
        if user.is_admin:
            print(f"✅ User {email} is already an admin.")
            return True
        
        user.is_admin = True
        db.commit()
        print(f"✅ Successfully promoted {email} to admin.")
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_admin.py <email>")
        sys.exit(1)
    
    email = sys.argv[1]
    create_admin(email)

