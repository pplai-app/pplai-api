#!/usr/bin/env python3
"""
Database migration runner for CI/CD
Runs migrations in order, safely handling already-applied migrations
"""
import os
import sys
import psycopg2
from pathlib import Path

def run_migration_file(conn, file_path):
    """Run a single migration file"""
    print(f"Running {file_path.name}...")
    with open(file_path, 'r') as f:
        sql = f.read()
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print(f"✅ {file_path.name} completed")
        return True
    except Exception as e:
        # If it's a "already exists" error, that's okay
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print(f"⚠️  {file_path.name} - already applied (skipping)")
            conn.rollback()
            return True
        else:
            print(f"❌ {file_path.name} failed: {e}")
            conn.rollback()
            return False

def main():
    # Get DATABASE_URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        sys.exit(1)
    
    # Connect to database
    try:
        conn = psycopg2.connect(database_url)
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    # Get migrations directory
    migrations_dir = Path(__file__).parent / 'migrations'
    if not migrations_dir.exists():
        print(f"❌ Migrations directory not found: {migrations_dir}")
        sys.exit(1)
    
    # Migration files in order
    migration_files = [
        'schema.sql',
        'add_password_to_users.sql',
        'add_user_id_to_tags.sql',
        'add_is_hidden_to_tags.sql',
        'add_location_to_contacts.sql',
        'add_is_admin_to_users.sql',
        'add_user_indexes.sql'
    ]
    
    print(f"\n📦 Running migrations from {migrations_dir}")
    print("=" * 50)
    
    success = True
    for migration_file in migration_files:
        file_path = migrations_dir / migration_file
        if not file_path.exists():
            print(f"⚠️  {migration_file} not found, skipping")
            continue
        
        if not run_migration_file(conn, file_path):
            success = False
            break
    
    conn.close()
    
    if success:
        print("\n✅ All migrations completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
