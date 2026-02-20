import sqlite3

db_path = r'D:\Side_project\MeetChi\apps\backend\meetchi_backup.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Delete all related records first
for table in ['transcript_segments', 'task_status', 'artifacts', 'meeting_tags']:
    c.execute(f'DELETE FROM {table}')
    print(f'Cleaned {table}: {c.rowcount} rows deleted')

c.execute('DELETE FROM meetings')
print(f'Deleted {c.rowcount} meetings')

conn.commit()

# Verify
count = c.execute('SELECT count(*) FROM meetings').fetchone()[0]
print(f'Remaining meetings: {count}')
conn.close()
print('DB cleanup complete!')
