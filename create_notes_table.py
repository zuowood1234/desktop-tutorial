from database import DBManager
from sqlalchemy import text

db = DBManager()
with db._get_connection() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS trading_notes (
            id SERIAL PRIMARY KEY,
            uid INTEGER REFERENCES users(uid),
            content TEXT NOT NULL,
            tags TEXT,
            is_public BOOLEAN DEFAULT FALSE,
            date_str VARCHAR(10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.commit()
print("Table created.")
