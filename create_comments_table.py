from database import DBManager
from sqlalchemy import text

db = DBManager()
with db._get_connection() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS note_comments (
            id SERIAL PRIMARY KEY,
            note_id INTEGER REFERENCES trading_notes(id) ON DELETE CASCADE,
            uid INTEGER REFERENCES users(uid),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.commit()
print("note_comments table created.")
