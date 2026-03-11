import sqlite3

def fix_db():
    conn = sqlite3.connect('meetchi_prod.db')
    cursor = conn.cursor()
    
    # Check meetings columns
    cursor.execute("PRAGMA table_info(meetings)")
    columns = [col[1] for col in cursor.fetchall()]
    print("Current columns in meetings table:", columns)
    
    # Add custom_prompt if missing
    if 'custom_prompt' not in columns:
        print("Adding custom_prompt")
        try:
            cursor.execute("ALTER TABLE meetings ADD COLUMN custom_prompt TEXT")
        except sqlite3.OperationalError as e:
            print(f"Error adding custom_prompt: {e}")
            
    # Add status if missing
    if 'status' not in columns:
        print("Adding status")
        try:
            # SQLAlchemy Enum generates a VARCHAR column in SQLite
            cursor.execute("ALTER TABLE meetings ADD COLUMN status VARCHAR DEFAULT 'PENDING'")
        except sqlite3.OperationalError as e:
            print(f"Error adding status: {e}")
            
    # Add title if missing
    if 'title' not in columns:
        print("Adding title")
        try:
            cursor.execute("ALTER TABLE meetings ADD COLUMN title VARCHAR DEFAULT 'Untitled Meeting'")
        except sqlite3.OperationalError as e:
            print(f"Error adding title: {e}")

    # Add template_name if missing
    if 'template_name' not in columns:
        print("Adding template_name")
        try:
            cursor.execute("ALTER TABLE meetings ADD COLUMN template_name VARCHAR(50) DEFAULT 'general'")
        except sqlite3.OperationalError as e:
            print(f"Error adding template_name: {e}")

    # Add audio_url if missing
    if 'audio_url' not in columns:
        print("Adding audio_url")
        try:
            cursor.execute("ALTER TABLE meetings ADD COLUMN audio_url VARCHAR")
        except sqlite3.OperationalError as e:
            print(f"Error adding audio_url: {e}")

    cursor.execute("PRAGMA table_info(meetings)")
    columns = [col[1] for col in cursor.fetchall()]
    print("New columns in meetings table:", columns)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    fix_db()
