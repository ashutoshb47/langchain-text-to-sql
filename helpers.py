import sqlite3

DB_PATH = "supermarket_sales.db"

def get_table_names() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name NOT LIKE 'sqlite_%'
        """)

        return [row[0] for row in cursor.fetchall()]

    finally:
        conn.close()

