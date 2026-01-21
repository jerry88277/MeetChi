import os
import sys
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Add parent directory to path to import app modules if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL not found in .env")
    sys.exit(1)

print(f"Connecting to database: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL)
    connection = engine.connect()
    
    # Reflect existing tables
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    # List of tables to drop in order (child tables first)
    tables_to_drop = ['transcript_segments', 'artifacts', 'task_status', 'meetings']
    
    for table_name in tables_to_drop:
        if table_name in metadata.tables:
            print(f"Dropping table: {table_name}...")
            metadata.tables[table_name].drop(engine)
            print(f"Table {table_name} dropped successfully.")
        else:
            print(f"Table {table_name} does not exist, skipping.")
            
    print("\nAll specified tables have been dropped.")
    print("Restart your backend application to recreate them with the latest schema.")
    
except Exception as e:
    print(f"\nAn error occurred: {e}")
    sys.exit(1)
finally:
    if 'connection' in locals():
        connection.close()
