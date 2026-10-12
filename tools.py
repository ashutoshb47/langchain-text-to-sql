import json

from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

import sqlite3

MAX_ROWS = 500

DB_PATH = "supermarket_sales.db"


@tool
def get_table_info(table_name: str) -> str:
    """
    Get the schema and first 3 rows of a SQLite table.
    Use this tool before generating SQL when table structure
    or column information is required.
    """

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get table schema
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        columns = cursor.fetchall()

        if not columns:
            return f"Table '{table_name}' does not exist."

        result = [f"TABLE: {table_name}", "", "SCHEMA:"]

        for column in columns:
            # PRAGMA table_info:
            # cid, name, type, notnull, default_value, pk
            _, name, data_type, not_null, default, primary_key = column

            result.append(
                f"- {name}: {data_type}"
            )

        # Get first 3 rows
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 3')

        rows = cursor.fetchall()
        column_names = [column[1] for column in columns]

        result.append("")
        result.append("FIRST 3 ROWS:")
        result.append(str(column_names))

        for row in rows:
            result.append(str(row))

        return "\n".join(result)

    except Exception as e:
        return f"Error retrieving table information: {str(e)}"

    finally:
        conn.close()

@tool
def execute_sql(query: str) -> str:
    """
    Execute a SQL SELECT query against the SQLite database.
    Returns JSON: {"columns": [...], "rows": [[...], ...], "row_count": n, "truncated": bool}.
    On failure returns JSON: {"error": "..."}.
    """
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)  # read-only
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        rows = cursor.fetchmany(MAX_ROWS + 1)
        columns = [d[0] for d in cursor.description] if cursor.description else []

        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]

        return json.dumps(
            {
                "columns": columns,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
                "truncated": truncated,
            },
            default=str,  # handles Decimal, datetime, bytes, etc.
        )

    except Exception as e:
        return json.dumps({"error": f"SQL execution error: {e}"})

    finally:
        conn.close()


