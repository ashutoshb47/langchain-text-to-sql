from langchain_core.tools import tool

import sqlite3

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
    Execute a SQL SELECT query against the SQLite database
    and return the query results.
    """

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(query)

        rows = cursor.fetchall()

        if not rows:
            return "Query executed successfully but returned no results."

        columns = [description[0] for description in cursor.description]

        result = [str(columns)]

        for row in rows:
            result.append(str(row))

        return "\n".join(result)

    except Exception as e:
        return f"SQL execution error: {str(e)}"

    finally:
        conn.close()