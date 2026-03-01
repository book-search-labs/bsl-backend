import os
import sys
from typing import Optional

import pymysql


MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

SYNC_SOURCE_NAME = os.environ.get("RAW_NODE_SYNC_SOURCE", "nlk_bridge")
SYNC_SOURCE_TYPE = os.environ.get("RAW_NODE_SYNC_TYPE", "nlk_json")
SYNC_FILE_NAME = os.environ.get("RAW_NODE_SYNC_FILE", "nlk_raw_nodes")
SYNC_REPLACE = os.environ.get("RAW_NODE_SYNC_REPLACE", "1") == "1"


def connect() -> pymysql.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=False,
    )


def table_exists(conn: pymysql.Connection, table_name: str) -> bool:
    sql = """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        LIMIT 1
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (MYSQL_DATABASE, table_name))
        return cursor.fetchone() is not None


def get_row_count(conn: pymysql.Connection, table_name: str) -> int:
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def sync_raw_node(conn: pymysql.Connection) -> int:
    with conn.cursor() as cursor:
        if SYNC_REPLACE:
            cursor.execute(
                """
                DELETE r
                FROM raw_node r
                JOIN ingest_batch b ON b.batch_id = r.batch_id
                WHERE b.source_name = %s
                """,
                (SYNC_SOURCE_NAME,),
            )
            cursor.execute("DELETE FROM ingest_batch WHERE source_name = %s", (SYNC_SOURCE_NAME,))

        cursor.execute(
            """
            INSERT INTO ingest_batch (
              source_name,
              source_type,
              file_name,
              status,
              started_at
            ) VALUES (%s, %s, %s, 'RUNNING', NOW())
            """,
            (SYNC_SOURCE_NAME, SYNC_SOURCE_TYPE, SYNC_FILE_NAME),
        )
        batch_id = int(cursor.lastrowid)

        inserted = cursor.execute(
            """
            INSERT INTO raw_node (
              batch_id,
              node_id,
              node_types,
              entity_kind,
              payload,
              payload_uri,
              payload_size_bytes,
              payload_hash,
              ingested_at
            )
            SELECT
              %s AS batch_id,
              n.record_id AS node_id,
              n.record_types AS node_types,
              CASE
                WHEN LOWER(n.dataset) = 'concept' THEN 'CONCEPT'
                WHEN LOWER(n.dataset) IN ('person', 'organization', 'library') THEN
                  CASE
                    WHEN CAST(n.raw_json AS CHAR) LIKE '%%nlon:Library%%' THEN 'LIBRARY'
                    ELSE 'AGENT'
                  END
                ELSE 'MATERIAL'
              END AS entity_kind,
              n.raw_json AS payload,
              NULL AS payload_uri,
              CHAR_LENGTH(CAST(n.raw_json AS CHAR)) AS payload_size_bytes,
              SHA2(CAST(n.raw_json AS CHAR), 256) AS payload_hash,
              COALESCE(n.updated_at, NOW()) AS ingested_at
            FROM nlk_raw_nodes n
            JOIN (
              SELECT record_id, MAX(raw_id) AS max_raw_id
              FROM nlk_raw_nodes
              GROUP BY record_id
            ) pick ON pick.max_raw_id = n.raw_id
            """,
            (batch_id,),
        )

        cursor.execute(
            """
            UPDATE ingest_batch
               SET status='SUCCESS',
                   finished_at=NOW(),
                   file_size_bytes=%s
             WHERE batch_id=%s
            """,
            (inserted, batch_id),
        )

    return inserted


def main() -> int:
    conn: Optional[pymysql.Connection] = None
    try:
        conn = connect()
        required_tables = ("nlk_raw_nodes", "raw_node", "ingest_batch")
        missing = [name for name in required_tables if not table_exists(conn, name)]
        if missing:
            print(f"[raw-node-sync] skipped (missing tables: {', '.join(missing)})")
            return 0

        source_count = get_row_count(conn, "nlk_raw_nodes")
        if source_count == 0:
            print("[raw-node-sync] skipped (nlk_raw_nodes is empty)")
            return 0

        inserted = sync_raw_node(conn)
        conn.commit()
        print(f"[raw-node-sync] synced rows: {inserted}")
        return 0
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"[raw-node-sync] failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
