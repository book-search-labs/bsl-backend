#!/usr/bin/env python3
import argparse
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import pymysql
except ImportError as exc:
    raise SystemExit(
        "PyMySQL is required. Install with: python3 -m pip install -r scripts/ingest/requirements.txt"
    ) from exc

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

LIBRARY_CONDITION = """
(
  (JSON_TYPE(JSON_EXTRACT(payload, '$."@type"'))='STRING'
    AND JSON_UNQUOTE(JSON_EXTRACT(payload, '$."@type"')) LIKE '%Library%')
  OR
  (JSON_TYPE(JSON_EXTRACT(payload, '$."@type"'))='ARRAY'
    AND JSON_SEARCH(JSON_EXTRACT(payload, '$."@type"'), 'one', '%Library%') IS NOT NULL)
)
"""


@dataclass
class ChunkStats:
    total: int = 0
    changed: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass
class EntityStats:
    total: int = 0
    changed: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    batches: int = 0


def log(msg: str) -> None:
    print(msg, flush=True)


def connect_mysql() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def get_latest_batch_id(conn) -> Optional[int]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT MAX(batch_id) AS batch_id FROM raw_node")
        row = cursor.fetchone()
        if not row or row.get("batch_id") is None:
            return None
        return int(row["batch_id"])


def get_checkpoint(conn, entity_kind: str, batch_id: int) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT last_raw_id FROM ingest_checkpoint WHERE entity_kind=%s AND batch_id=%s",
            (entity_kind, batch_id),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return int(row.get("last_raw_id") or 0)


def update_checkpoint(conn, entity_kind: str, batch_id: int, last_raw_id: int, processed: int) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingest_checkpoint (entity_kind, batch_id, last_raw_id, processed_count)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              last_raw_id=VALUES(last_raw_id),
              processed_count=processed_count + VALUES(processed_count),
              updated_at=NOW()
            """,
            (entity_kind, batch_id, last_raw_id, processed),
        )
    conn.commit()


def drop_temp_tables(cursor) -> None:
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS tmp_changed")
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS tmp_chunk")


def create_chunk_table(cursor, sql: str, params: Tuple) -> int:
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS tmp_chunk")
    cursor.execute(sql, params)
    cursor.execute("SELECT COUNT(*) AS cnt FROM tmp_chunk")
    row = cursor.fetchone()
    return int(row.get("cnt") or 0)


def create_changed_table(cursor, entity_table: str, id_column: str) -> ChunkStats:
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS tmp_changed")
    cursor.execute(
        f"""
        CREATE TEMPORARY TABLE tmp_changed AS
        SELECT c.node_id AS id, c.raw_id
        FROM tmp_chunk c
        LEFT JOIN {entity_table} t ON t.{id_column} = c.node_id
        WHERE t.{id_column} IS NULL OR t.last_payload_hash <> c.payload_hash
        """
    )

    stats = ChunkStats()
    cursor.execute("SELECT COUNT(*) AS cnt FROM tmp_chunk")
    stats.total = int(cursor.fetchone().get("cnt") or 0)
    cursor.execute("SELECT COUNT(*) AS cnt FROM tmp_changed")
    stats.changed = int(cursor.fetchone().get("cnt") or 0)
    cursor.execute(
        f"SELECT COUNT(*) AS cnt FROM tmp_changed c LEFT JOIN {entity_table} t ON t.{id_column} = c.id WHERE t.{id_column} IS NULL"
    )
    stats.inserted = int(cursor.fetchone().get("cnt") or 0)
    stats.updated = max(stats.changed - stats.inserted, 0)
    stats.skipped = max(stats.total - stats.changed, 0)
    return stats


def max_raw_id(cursor) -> int:
    cursor.execute("SELECT MAX(raw_id) AS max_id FROM tmp_chunk")
    row = cursor.fetchone()
    return int(row.get("max_id") or 0)


def process_concept(conn, batch_id: int, last_raw_id: int, batch_size: int) -> Tuple[int, ChunkStats]:
    chunk_sql = (
        "CREATE TEMPORARY TABLE tmp_chunk AS "
        "SELECT raw_id, node_id, payload, payload_hash "
        "FROM raw_node "
        "WHERE batch_id=%s AND entity_kind='CONCEPT' AND raw_id > %s "
        "ORDER BY raw_id LIMIT %s"
    )
    with conn.cursor() as cursor:
        total = create_chunk_table(cursor, chunk_sql, (batch_id, last_raw_id, batch_size))
        if total == 0:
            drop_temp_tables(cursor)
            return 0, ChunkStats()

        stats = create_changed_table(cursor, "concept", "concept_id")
        if stats.changed:
            cursor.execute(
                """
                INSERT INTO concept (
                  concept_id,
                  pref_label,
                  label,
                  broader_concept_id,
                  scheme_id,
                  raw_payload,
                  last_raw_id,
                  last_payload_hash,
                  created_at,
                  updated_at
                )
                SELECT
                  c.node_id AS concept_id,
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.prefLabel')), '') AS pref_label,
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.label')), '') AS label,
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.broader')), '') AS broader_concept_id,
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.inScheme')), '') AS scheme_id,
                  c.payload AS raw_payload,
                  c.raw_id AS last_raw_id,
                  c.payload_hash AS last_payload_hash,
                  NOW(),
                  NOW()
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                WHERE c.node_id IS NOT NULL AND c.node_id <> ''
                ON DUPLICATE KEY UPDATE
                  pref_label=VALUES(pref_label),
                  label=VALUES(label),
                  broader_concept_id=VALUES(broader_concept_id),
                  scheme_id=VALUES(scheme_id),
                  raw_payload=VALUES(raw_payload),
                  last_raw_id=VALUES(last_raw_id),
                  last_payload_hash=VALUES(last_payload_hash),
                  updated_at=NOW()
                """
            )
        max_id = max_raw_id(cursor)
        drop_temp_tables(cursor)
    conn.commit()
    return max_id, stats


def process_agent(conn, batch_id: int, last_raw_id: int, batch_size: int) -> Tuple[int, ChunkStats]:
    chunk_sql = (
        "CREATE TEMPORARY TABLE tmp_chunk AS "
        "SELECT raw_id, node_id, payload, payload_hash "
        "FROM raw_node "
        "WHERE batch_id=%s AND entity_kind='AGENT' AND raw_id > %s "
        f"AND NOT {LIBRARY_CONDITION} "
        "ORDER BY raw_id LIMIT %s"
    )
    with conn.cursor() as cursor:
        total = create_chunk_table(cursor, chunk_sql, (batch_id, last_raw_id, batch_size))
        if total == 0:
            drop_temp_tables(cursor)
            return 0, ChunkStats()

        stats = create_changed_table(cursor, "agent", "agent_id")
        if stats.changed:
            cursor.execute(
                """
                INSERT INTO agent (
                  agent_id,
                  agent_type,
                  pref_label,
                  label,
                  name,
                  isni,
                  url,
                  location,
                  gender,
                  birth_year,
                  death_year,
                  corporate_name,
                  job_title,
                  date_of_establishment,
                  date_published,
                  modified_at,
                  field_of_activity_json,
                  source_json,
                  raw_payload,
                  last_raw_id,
                  last_payload_hash,
                  created_at,
                  updated_at
                )
                SELECT
                  COALESCE(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$."@id"')), c.node_id) AS agent_id,
                  CASE
                    WHEN (
                      (JSON_TYPE(JSON_EXTRACT(c.payload, '$."rdf:type"')) = 'STRING'
                        AND JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$."rdf:type"')) LIKE '%/Person%')
                        OR
                      (JSON_TYPE(JSON_EXTRACT(c.payload, '$."rdf:type"')) = 'ARRAY'
                        AND JSON_SEARCH(JSON_EXTRACT(c.payload, '$."rdf:type"'), 'one', '%/Person%') IS NOT NULL)
                    ) THEN 'PERSON' ELSE 'ORG'
                  END AS agent_type,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.prefLabel')) AS pref_label,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.label')) AS label,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.name')) AS name,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.isni')) AS isni,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.url')) AS url,
                  COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.location')),
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$."schema:location"'))
                  ) AS location,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.gender')) AS gender,
                  CASE
                    WHEN JSON_EXTRACT(c.payload, '$.birthYear') IS NULL THEN NULL
                    ELSE CAST(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.birthYear')), '^^', 1) AS UNSIGNED)
                  END AS birth_year,
                  CASE
                    WHEN JSON_EXTRACT(c.payload, '$.deathYear') IS NULL THEN NULL
                    ELSE CAST(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.deathYear')), '^^', 1) AS UNSIGNED)
                  END AS death_year,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.corporateName')) AS corporate_name,
                  CASE
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.jobTitle'))='ARRAY'
                      THEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.jobTitle[0]'))
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.jobTitle'))='STRING'
                      THEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.jobTitle'))
                    ELSE NULL
                  END AS job_title,
                  CASE
                    WHEN JSON_EXTRACT(c.payload, '$.dateOfEstablishment') IS NULL THEN NULL
                    ELSE
                      CASE
                        WHEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment'))
                          REGEXP '^[0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])$'
                            THEN STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '%Y%m%d')
                        WHEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment'))
                          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                            THEN STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '%Y-%m-%d')
                        WHEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment'))
                          REGEXP '^[0-9]{4}/[0-9]{2}/[0-9]{2}$'
                            THEN STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '%Y/%m/%d')
                        WHEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment'))
                          REGEXP '^[0-9]{4}\.[0-9]{1,2}\.$'
                            THEN STR_TO_DATE(
                              CONCAT(
                                SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '.', 1),
                                '-',
                                LPAD(SUBSTRING_INDEX(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '.', 2), '.', -1), 2, '0'),
                                '-01'
                              ),
                              '%Y-%m-%d'
                            )
                        WHEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment'))
                          REGEXP '^[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,2}\.$'
                            THEN STR_TO_DATE(
                              CONCAT(
                                SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '.', 1),
                                '-',
                                LPAD(SUBSTRING_INDEX(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '.', 2), '.', -1), 2, '0'),
                                '-',
                                LPAD(SUBSTRING_INDEX(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '.', 3), '.', -1), 2, '0')
                              ),
                              '%Y-%m-%d'
                            )
                        WHEN JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')) REGEXP '^[0-9]{4}$'
                            THEN STR_TO_DATE(CONCAT(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.dateOfEstablishment')), '-01-01'), '%Y-%m-%d')
                        ELSE NULL
                      END
                  END AS date_of_establishment,
                  CASE
                    WHEN JSON_EXTRACT(c.payload, '$.datePublished') IS NULL THEN NULL
                    ELSE
                      CASE
                        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.datePublished')), '^^', 1)
                          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$'
                          THEN STR_TO_DATE(
                            SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.datePublished')), '^^', 1),
                            '%Y-%m-%dT%H:%i:%s'
                          )
                        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.datePublished')), '^^', 1)
                          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                          THEN STR_TO_DATE(
                            SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.datePublished')), '^^', 1),
                            '%Y-%m-%d'
                          )
                        ELSE NULL
                      END
                  END AS date_published,
                  CASE
                    WHEN JSON_EXTRACT(c.payload, '$.modified') IS NULL THEN NULL
                    ELSE
                      CASE
                        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.modified')), '^^', 1)
                          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$'
                          THEN STR_TO_DATE(
                            SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.modified')), '^^', 1),
                            '%Y-%m-%dT%H:%i:%s'
                          )
                        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.modified')), '^^', 1)
                          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                          THEN STR_TO_DATE(
                            SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.modified')), '^^', 1),
                            '%Y-%m-%d'
                          )
                        ELSE NULL
                      END
                  END AS modified_at,
                  JSON_EXTRACT(c.payload, '$.fieldOfActivity') AS field_of_activity_json,
                  JSON_EXTRACT(c.payload, '$.source') AS source_json,
                  c.payload AS raw_payload,
                  c.raw_id AS last_raw_id,
                  c.payload_hash AS last_payload_hash,
                  NOW(),
                  NOW()
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                WHERE COALESCE(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$."@id"')), c.node_id) IS NOT NULL
                ON DUPLICATE KEY UPDATE
                  agent_type=VALUES(agent_type),
                  pref_label=VALUES(pref_label),
                  label=VALUES(label),
                  name=VALUES(name),
                  isni=VALUES(isni),
                  url=VALUES(url),
                  location=VALUES(location),
                  gender=VALUES(gender),
                  birth_year=VALUES(birth_year),
                  death_year=VALUES(death_year),
                  corporate_name=VALUES(corporate_name),
                  job_title=VALUES(job_title),
                  date_of_establishment=VALUES(date_of_establishment),
                  date_published=VALUES(date_published),
                  modified_at=VALUES(modified_at),
                  field_of_activity_json=VALUES(field_of_activity_json),
                  source_json=VALUES(source_json),
                  raw_payload=VALUES(raw_payload),
                  last_raw_id=VALUES(last_raw_id),
                  last_payload_hash=VALUES(last_payload_hash),
                  updated_at=NOW()
                """
            )

            cursor.execute("DELETE FROM agent_alt_label WHERE agent_id IN (SELECT id FROM tmp_changed)")
            cursor.execute(
                """
                INSERT IGNORE INTO agent_alt_label (agent_id, alt_label)
                SELECT
                  c.node_id AS agent_id,
                  jt.alt_label
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                JOIN JSON_TABLE(
                  CASE
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload,'$.altLabel'))='ARRAY' THEN JSON_EXTRACT(c.payload,'$.altLabel')
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload,'$.altLabel')) IN ('STRING','OBJECT') THEN JSON_ARRAY(JSON_EXTRACT(c.payload,'$.altLabel'))
                    ELSE JSON_ARRAY()
                  END,
                  '$[*]' COLUMNS(alt_label VARCHAR(512) PATH '$')
                ) jt
                WHERE jt.alt_label IS NOT NULL AND jt.alt_label <> ''
                """
            )

            cursor.execute("DELETE FROM agent_language WHERE agent_id IN (SELECT id FROM tmp_changed)")
            cursor.execute(
                """
                INSERT IGNORE INTO agent_language (agent_id, language)
                SELECT
                  c.node_id AS agent_id,
                  jt.lang
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                JOIN JSON_TABLE(
                  CASE
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload,'$.associatedLanguage'))='ARRAY' THEN JSON_EXTRACT(c.payload,'$.associatedLanguage')
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload,'$.associatedLanguage')) IN ('STRING','OBJECT') THEN JSON_ARRAY(JSON_EXTRACT(c.payload,'$.associatedLanguage'))
                    ELSE JSON_ARRAY()
                  END,
                  '$[*]' COLUMNS(lang VARCHAR(64) PATH '$')
                ) jt
                WHERE jt.lang IS NOT NULL AND jt.lang <> ''
                """
            )
        max_id = max_raw_id(cursor)
        drop_temp_tables(cursor)
    conn.commit()
    return max_id, stats


def process_library(conn, batch_id: int, last_raw_id: int, batch_size: int) -> Tuple[int, ChunkStats]:
    chunk_sql = (
        "CREATE TEMPORARY TABLE tmp_chunk AS "
        "SELECT raw_id, node_id, payload, payload_hash "
        "FROM raw_node "
        "WHERE batch_id=%s AND raw_id > %s "
        "AND (entity_kind='LIBRARY' OR (entity_kind='AGENT' AND " + LIBRARY_CONDITION + ")) "
        "ORDER BY raw_id LIMIT %s"
    )
    with conn.cursor() as cursor:
        total = create_chunk_table(cursor, chunk_sql, (batch_id, last_raw_id, batch_size))
        if total == 0:
            drop_temp_tables(cursor)
            return 0, ChunkStats()

        stats = create_changed_table(cursor, "library", "library_id")
        if stats.changed:
            cursor.execute(
                """
                INSERT INTO library (
                  library_id,
                  identifier,
                  label,
                  keyword,
                  library_type,
                  opening_year,
                  date_of_opening,
                  is_closed,
                  date_of_closed,
                  summer_open_time,
                  winter_open_time,
                  fax_number,
                  phone,
                  location_uri,
                  homepage_json,
                  subject,
                  raw_payload,
                  last_raw_id,
                  last_payload_hash,
                  created_at,
                  updated_at
                )
                SELECT
                  x.library_id,
                  x.identifier,
                  x.label,
                  x.keyword,
                  x.library_type,
                  x.opening_year,
                  CASE
                    WHEN x.opening_raw IS NULL OR x.opening_raw = '' THEN NULL
                    WHEN x.opening_raw REGEXP '^[0-9]{4}/[0-9]{2}/[0-9]{2}$' THEN
                      CASE
                        WHEN
                          YEAR(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED)
                          AND MONTH(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)
                          AND DAY(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)
                        THEN
                          DATE_ADD(
                            DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                     INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                            INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                          )
                        ELSE NULL
                      END
                    WHEN x.opening_raw REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
                      CASE
                        WHEN
                          YEAR(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED)
                          AND MONTH(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)
                          AND DAY(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)
                        THEN
                          DATE_ADD(
                            DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                     INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
                            INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
                          )
                        ELSE NULL
                      END
                    WHEN x.opening_raw REGEXP '^[0-9]{8}$' THEN
                      CASE
                        WHEN
                          YEAR(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED)
                          AND MONTH(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)
                          AND DAY(
                            DATE_ADD(
                              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                       INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
                              INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
                            )
                          ) = CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)
                        THEN
                          DATE_ADD(
                            DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                                     INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
                            INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
                          )
                        ELSE NULL
                      END
                    ELSE NULL
                  END AS date_of_opening,
                  x.is_closed,
                  x.date_of_closed,
                  x.summer_open_time,
                  x.winter_open_time,
                  x.fax_number,
                  x.phone,
                  x.location_uri,
                  x.homepage_json,
                  x.subject,
                  x.raw_payload,
                  x.last_raw_id,
                  x.last_payload_hash,
                  NOW(),
                  NOW()
                FROM (
                  SELECT
                    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$."@id"')), c.node_id) AS library_id,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.identifier')) AS identifier,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.label')) AS label,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.keyword')) AS keyword,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.libraryType')) AS library_type,
                    CAST(JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.openingYear')) AS UNSIGNED) AS opening_year,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.dateOfOpening')) AS opening_raw,
                    CASE
                      WHEN JSON_EXTRACT(c.payload,'$.isClosed') IS NULL THEN NULL
                      WHEN LOWER(JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.isClosed'))) IN ('true','1','yes','y') THEN 1
                      ELSE 0
                    END AS is_closed,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.dateOfClosed')) AS date_of_closed,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.summerOpenTime')) AS summer_open_time,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.winterOpenTime')) AS winter_open_time,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.faxNumber')) AS fax_number,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.phone')) AS phone,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.location')) AS location_uri,
                    JSON_EXTRACT(c.payload,'$.homepage') AS homepage_json,
                    JSON_UNQUOTE(JSON_EXTRACT(c.payload,'$.subject')) AS subject,
                    c.payload AS raw_payload,
                    c.raw_id AS last_raw_id,
                    c.payload_hash AS last_payload_hash
                  FROM tmp_chunk c
                  JOIN tmp_changed t ON t.id = c.node_id
                  WHERE """
                + LIBRARY_CONDITION +
                """
                ) x
                ON DUPLICATE KEY UPDATE
                  identifier=VALUES(identifier),
                  label=VALUES(label),
                  keyword=VALUES(keyword),
                  library_type=VALUES(library_type),
                  opening_year=VALUES(opening_year),
                  date_of_opening=VALUES(date_of_opening),
                  is_closed=VALUES(is_closed),
                  date_of_closed=VALUES(date_of_closed),
                  summer_open_time=VALUES(summer_open_time),
                  winter_open_time=VALUES(winter_open_time),
                  fax_number=VALUES(fax_number),
                  phone=VALUES(phone),
                  location_uri=VALUES(location_uri),
                  homepage_json=VALUES(homepage_json),
                  subject=VALUES(subject),
                  raw_payload=VALUES(raw_payload),
                  last_raw_id=VALUES(last_raw_id),
                  last_payload_hash=VALUES(last_payload_hash),
                  updated_at=NOW()
                """
            )
        max_id = max_raw_id(cursor)
        drop_temp_tables(cursor)
    conn.commit()
    return max_id, stats


def process_material(conn, batch_id: int, last_raw_id: int, batch_size: int) -> Tuple[int, ChunkStats]:
    chunk_sql = (
        "CREATE TEMPORARY TABLE tmp_chunk AS "
        "SELECT raw_id, node_id, payload, payload_hash "
        "FROM raw_node "
        "WHERE batch_id=%s AND entity_kind='MATERIAL' AND raw_id > %s AND node_id LIKE 'nlk:%' "
        "ORDER BY raw_id LIMIT %s"
    )
    with conn.cursor() as cursor:
        total = create_chunk_table(cursor, chunk_sql, (batch_id, last_raw_id, batch_size))
        if total == 0:
            drop_temp_tables(cursor)
            return 0, ChunkStats()

        stats = create_changed_table(cursor, "material", "material_id")
        if stats.changed:
            cursor.execute(
                """
                INSERT INTO material (
                  material_id,
                  material_kind,
                  title,
                  subtitle,
                  label,
                  description,
                  publisher,
                  publication_place,
                  issued_year,
                  date_published,
                  language,
                  raw_payload,
                  last_raw_id,
                  last_payload_hash,
                  created_at,
                  updated_at
                )
                SELECT
                  c.node_id AS material_id,
                  CASE
                    WHEN JSON_CONTAINS(
                      JSON_EXTRACT(c.payload, '$."@type"'),
                      JSON_QUOTE('bibo:Book')
                    ) THEN 'BOOK'
                    ELSE 'OFFLINE'
                  END AS material_kind,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.title')) AS title,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.remainderOfTitle')) AS subtitle,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.label')) AS label,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.description')) AS description,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.publisher')) AS publisher,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.publicationPlace')) AS publication_place,
                  CAST(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.issuedYear')) AS UNSIGNED) AS issued_year,
                  CASE
                    WHEN JSON_EXTRACT(c.payload, '$.datePublished') IS NULL THEN NULL
                    WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.datePublished')), '^^', 1)
                      REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$'
                    THEN STR_TO_DATE(
                      SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.datePublished')), '^^', 1),
                      '%Y-%m-%dT%H:%i:%s'
                    )
                    ELSE NULL
                  END AS date_published,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.language')) AS language,
                  c.payload AS raw_payload,
                  c.raw_id AS last_raw_id,
                  c.payload_hash AS last_payload_hash,
                  NOW(),
                  NOW()
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                WHERE c.node_id IS NOT NULL AND c.node_id <> ''
                ON DUPLICATE KEY UPDATE
                  material_kind=VALUES(material_kind),
                  title=VALUES(title),
                  subtitle=VALUES(subtitle),
                  label=VALUES(label),
                  description=VALUES(description),
                  publisher=VALUES(publisher),
                  publication_place=VALUES(publication_place),
                  issued_year=VALUES(issued_year),
                  date_published=VALUES(date_published),
                  language=VALUES(language),
                  raw_payload=VALUES(raw_payload),
                  last_raw_id=VALUES(last_raw_id),
                  last_payload_hash=VALUES(last_payload_hash),
                  updated_at=NOW()
                """
            )

            cursor.execute("DELETE FROM material_identifier WHERE material_id IN (SELECT id FROM tmp_changed)")
            cursor.execute(
                """
                INSERT IGNORE INTO material_identifier (material_id, scheme, value)
                SELECT
                  c.node_id AS material_id,
                  'ISBN' AS scheme,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.isbn')) AS value
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                WHERE JSON_EXTRACT(c.payload, '$.isbn') IS NOT NULL
                  AND JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.isbn')) <> ''
                """
            )
            cursor.execute(
                """
                INSERT IGNORE INTO material_identifier (material_id, scheme, value)
                SELECT
                  c.node_id AS material_id,
                  'NLK_ITEMNO' AS scheme,
                  JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.itemNumberOfNLK')) AS value
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                WHERE JSON_EXTRACT(c.payload, '$.itemNumberOfNLK') IS NOT NULL
                  AND JSON_UNQUOTE(JSON_EXTRACT(c.payload, '$.itemNumberOfNLK')) <> ''
                """
            )
            cursor.execute(
                """
                INSERT IGNORE INTO material_identifier (material_id, scheme, value)
                SELECT
                  c.node_id AS material_id,
                  'NLK_LOCALHOLDING' AS scheme,
                  jt.val AS value
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                JOIN JSON_TABLE(
                  CASE
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.localHolding'))='ARRAY'
                      THEN JSON_EXTRACT(c.payload, '$.localHolding')
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.localHolding')) IN ('STRING','OBJECT')
                      THEN JSON_ARRAY(JSON_EXTRACT(c.payload, '$.localHolding'))
                    ELSE JSON_ARRAY()
                  END,
                  '$[*]' COLUMNS (val VARCHAR(128) PATH '$')
                ) jt
                WHERE jt.val IS NOT NULL AND jt.val <> ''
                """
            )

            cursor.execute("DELETE FROM material_agent WHERE material_id IN (SELECT id FROM tmp_changed)")
            cursor.execute(
                """
                INSERT IGNORE INTO material_agent (material_id, agent_id, role)
                SELECT
                  c.node_id AS material_id,
                  CASE
                    WHEN JSON_TYPE(j.elem) = 'OBJECT' THEN JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"'))
                    WHEN JSON_TYPE(j.elem) = 'STRING' THEN JSON_UNQUOTE(j.elem)
                    ELSE NULL
                  END AS agent_id,
                  'CREATOR' AS role
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                JOIN JSON_TABLE(
                  JSON_MERGE_PRESERVE(
                    CASE
                      WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.creator'))='ARRAY'
                        THEN JSON_EXTRACT(c.payload, '$.creator')
                      WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.creator')) IN ('OBJECT','STRING')
                        THEN JSON_ARRAY(JSON_EXTRACT(c.payload, '$.creator'))
                      ELSE JSON_ARRAY()
                      END,
                    CASE
                      WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$."dcterms:creator"'))='ARRAY'
                        THEN JSON_EXTRACT(c.payload, '$."dcterms:creator"')
                      WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$."dcterms:creator"')) IN ('OBJECT','STRING')
                        THEN JSON_ARRAY(JSON_EXTRACT(c.payload, '$."dcterms:creator"'))
                      ELSE JSON_ARRAY()
                      END
                  ),
                  '$[*]' COLUMNS (elem JSON PATH '$')
                ) j
                WHERE (
                  (JSON_TYPE(j.elem)='OBJECT' AND JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"')) LIKE 'nlk:%')
                  OR (JSON_TYPE(j.elem)='STRING' AND JSON_UNQUOTE(j.elem) LIKE 'nlk:%')
                )
                """
            )

            cursor.execute("DELETE FROM material_concept WHERE material_id IN (SELECT id FROM tmp_changed)")
            cursor.execute(
                """
                INSERT IGNORE INTO material_concept (material_id, concept_id, role)
                SELECT
                  c.node_id AS material_id,
                  CASE
                    WHEN JSON_TYPE(j.elem) = 'OBJECT' THEN JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"'))
                    WHEN JSON_TYPE(j.elem) = 'STRING' THEN JSON_UNQUOTE(j.elem)
                    ELSE NULL
                  END AS concept_id,
                  'SUBJECT' AS role
                FROM tmp_chunk c
                JOIN tmp_changed t ON t.id = c.node_id
                JOIN JSON_TABLE(
                  CASE
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.subject'))='ARRAY'
                      THEN JSON_EXTRACT(c.payload, '$.subject')
                    WHEN JSON_TYPE(JSON_EXTRACT(c.payload, '$.subject')) IN ('OBJECT','STRING')
                      THEN JSON_ARRAY(JSON_EXTRACT(c.payload, '$.subject'))
                    ELSE JSON_ARRAY()
                  END,
                  '$[*]' COLUMNS (elem JSON PATH '$')
                ) j
                WHERE (
                  (JSON_TYPE(j.elem)='OBJECT' AND JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"')) LIKE 'nlk:%')
                  OR (JSON_TYPE(j.elem)='STRING' AND JSON_UNQUOTE(j.elem) LIKE 'nlk:%')
                )
                """
            )
        max_id = max_raw_id(cursor)
        drop_temp_tables(cursor)
    conn.commit()
    return max_id, stats


def run_entity(
    conn,
    entity_kind: str,
    batch_id: int,
    batch_size: int,
    max_batches: Optional[int],
    handler,
) -> EntityStats:
    stats = EntityStats()
    last_raw_id = get_checkpoint(conn, entity_kind, batch_id)
    log(f"[etl] {entity_kind} start from raw_id>{last_raw_id} batch_id={batch_id}")

    batch_count = 0
    while True:
        max_id, chunk_stats = handler(conn, batch_id, last_raw_id, batch_size)
        if max_id == 0:
            break

        batch_count += 1
        last_raw_id = max_id

        update_checkpoint(conn, entity_kind, batch_id, last_raw_id, chunk_stats.total)

        stats.total += chunk_stats.total
        stats.changed += chunk_stats.changed
        stats.inserted += chunk_stats.inserted
        stats.updated += chunk_stats.updated
        stats.skipped += chunk_stats.skipped
        stats.batches = batch_count

        log(
            f"[etl] {entity_kind} batch#{batch_count} raw_id<= {last_raw_id} "
            f"total={chunk_stats.total} changed={chunk_stats.changed} "
            f"inserted={chunk_stats.inserted} updated={chunk_stats.updated} skipped={chunk_stats.skipped}"
        )

        if max_batches and batch_count >= max_batches:
            break

    log(
        f"[etl] {entity_kind} done batches={stats.batches} total={stats.total} "
        f"changed={stats.changed} inserted={stats.inserted} updated={stats.updated} skipped={stats.skipped}"
    )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical ETL incremental upsert")
    parser.add_argument("--batch-id", type=int, help="raw_node batch_id to process")
    parser.add_argument("--batch-size", type=int, default=1000, help="raw_node rows per batch")
    parser.add_argument(
        "--entity-kinds",
        type=str,
        default="CONCEPT,AGENT,LIBRARY,MATERIAL",
        help="comma-separated entity kinds",
    )
    parser.add_argument("--max-batches", type=int, help="limit number of batches per entity")

    args = parser.parse_args()

    conn = connect_mysql()
    try:
        batch_id = args.batch_id or get_latest_batch_id(conn)
        if not batch_id:
            log("[etl] raw_node is empty; nothing to process")
            return 0

        handlers = {
            "CONCEPT": process_concept,
            "AGENT": process_agent,
            "LIBRARY": process_library,
            "MATERIAL": process_material,
        }
        kinds = [kind.strip().upper() for kind in args.entity_kinds.split(",") if kind.strip()]
        for kind in kinds:
            handler = handlers.get(kind)
            if not handler:
                log(f"[etl] skip unknown entity kind: {kind}")
                continue
            run_entity(conn, kind, batch_id, args.batch_size, args.max_batches, handler)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"[etl] failed: {exc}")
        sys.exit(1)
