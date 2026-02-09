
from database import DBManager
from sqlalchemy import text
import pandas as pd

def check_cloud():
    db = DBManager()
    with db._get_connection() as conn:
        df = pd.read_sql_query(text("SELECT code, name FROM stock_info WHERE code IN ('000960', '300102', '688981')"), conn)
        print("--- Cloud Table Verification ---")
        print(df)
        
        total = conn.execute(text("SELECT count(*) FROM stock_info")).scalar()
        print(f"\nTotal entries in cloud: {total}")

if __name__ == "__main__":
    check_cloud()
