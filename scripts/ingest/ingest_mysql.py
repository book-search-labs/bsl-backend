import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymysql
from pymysql import err as pymysql_err
from pymysql.constants import CLIENT

from lib.checkpoints import CheckpointStore
from lib.extract import (
  extract_contributors,
  extract_edition_labels,
  extract_identifiers,
  extract_issued_year,
  extract_language,
  extract_publisher,
  extract_record_id,
  extract_title,
  extract_types,
  extract_updated_at,
  extract_volume,
)
from lib.parser import detect_format, iter_jsonld_graph, iter_ndjson
from lib.paths import checkpoints_dir, data_root, dataset_name, iter_input_files, raw_dir

# Tuning knobs (env override)
BATCH_SIZE = int(os.environ.get("MYSQL_BATCH_SIZE", "50000"))
CHUNK_SIZE = int(os.environ.get("MYSQL_CHUNK_SIZE", "5000"))
PROGRESS_EVERY = int(os.environ.get("MYSQL_PROGRESS_EVERY", "5000"))
RESET = os.environ.get("RESET", "0") == "1"
FAST_MODE = os.environ.get("FAST_MODE", "0") == "1"
BULK_MODE = os.environ.get("MYSQL_BULK_MODE", "0") == "1"
LOAD_BATCH_ROWS = int(os.environ.get("MYSQL_LOAD_BATCH", "100000"))
LOAD_TMP_DIR_ENV = os.environ.get("MYSQL_LOAD_TMP_DIR")
KEEP_LOAD_FILES = os.environ.get("MYSQL_KEEP_LOAD_FILES", "0") == "1"

RAW_HASH_MODE = os.environ.get("RAW_HASH_MODE")
if RAW_HASH_MODE is None:
  RAW_HASH_MODE = "record_id" if FAST_MODE else "json"
RAW_HASH_MODE = RAW_HASH_MODE.lower()

STORE_BIBLIO_RAW_ENV = os.environ.get("STORE_BIBLIO_RAW")
if STORE_BIBLIO_RAW_ENV is None:
  STORE_BIBLIO_RAW = not FAST_MODE
else:
  STORE_BIBLIO_RAW = STORE_BIBLIO_RAW_ENV == "1"

# Retry knobs
MAX_RECONNECT_RETRIES = int(os.environ.get("MYSQL_RECONNECT_RETRIES", "3"))
RECONNECT_BACKOFF_BASE_SEC = float(os.environ.get("MYSQL_RECONNECT_BACKOFF_BASE_SEC", "1.0"))
RECONNECT_BACKOFF_MAX_SEC = float(os.environ.get("MYSQL_RECONNECT_BACKOFF_MAX_SEC", "8.0"))

# Optional: reduce per-session overhead during bulk ingest (safe for your schema: no FK usage shown)
DISABLE_FK_CHECKS = os.environ.get("MYSQL_DISABLE_FK_CHECKS", "1") == "1"
DISABLE_UNIQUE_CHECKS = os.environ.get("MYSQL_DISABLE_UNIQUE_CHECKS", "1") == "1"

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

BIBLIO_DATASETS = {
  "offline",
  "online",
  "book",
  "serial",
  "thesis",
  "audiovisual",
  "govermentpublication",
  "governmentpublication",
}

DUMPS_KWARGS = {"ensure_ascii": False, "separators": (",", ":")}
LOCAL_INFILE_WARNED = False

RAW_COLUMNS = [
  "record_id",
  "record_types",
  "dataset",
  "source_file",
  "updated_at",
  "updated_at_raw",
  "raw_json",
  "raw_hash",
]

BIBLIO_COLUMNS = [
  "record_id",
  "dataset",
  "source_file",
  "title",
  "title_en",
  "authors",
  "authors_text",
  "publisher_name",
  "issued_year",
  "language_code",
  "volume",
  "edition_labels",
  "identifiers",
  "updated_at",
  "updated_at_raw",
  "raw_json",
]

if LOAD_TMP_DIR_ENV:
  LOAD_TMP_DIR = Path(LOAD_TMP_DIR_ENV)
else:
  LOAD_TMP_DIR = data_root() / "tmp"


def compute_raw_hash(record_id: str, raw_json: str) -> str:
  if RAW_HASH_MODE == "json":
    source = raw_json
  else:
    source = record_id
  return hashlib.sha256(source.encode("utf-8")).hexdigest()


def sanitize_text(value: str) -> str:
  return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def format_datetime(value: Any) -> str:
  if isinstance(value, datetime):
    return value.strftime("%Y-%m-%d %H:%M:%S")
  if hasattr(value, "isoformat"):
    return value.isoformat(sep=" ")
  return str(value)


def format_field(value: Any) -> str:
  if value is None:
    return r"\N"
  if isinstance(value, str):
    return sanitize_text(value)
  if isinstance(value, (int, float, bool)):
    return str(value)
  return sanitize_text(format_datetime(value))


def escape_mysql_path(path: str) -> str:
  return path.replace("\\", "\\\\").replace("'", "\\'")


class LoadDataBuffer:
  def __init__(self, table_name: str, columns: List[str]) -> None:
    self.table_name = table_name
    self.columns = columns
    self.count = 0
    self.path: Optional[Path] = None
    self.handle = None
    self.writer = None
    self._open()

  def _open(self) -> None:
    LOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
      mode="w",
      encoding="utf-8",
      newline="",
      delete=False,
      dir=str(LOAD_TMP_DIR),
      prefix=f"{self.table_name}_",
      suffix=".tsv",
    )
    self.handle = handle
    self.path = Path(handle.name)
    self.writer = None

  def write_row(self, row: Tuple[Any, ...]) -> None:
    if not self.handle:
      raise RuntimeError("LoadDataBuffer handle not initialized")
    line = "\t".join(format_field(value) for value in row)
    self.handle.write(f"{line}\n")
    self.count += 1

  def flush(self, cursor: pymysql.cursors.Cursor) -> None:
    if self.count == 0 or not self.path or not self.handle:
      return
    self.handle.flush()
    os.fsync(self.handle.fileno())
    columns_sql = ", ".join(f"@{column}" for column in self.columns)
    set_sql = ", ".join(f"`{column}`=NULLIF(@{column}, '\\\\N')" for column in self.columns)
    path_sql = escape_mysql_path(str(self.path))
    load_sql = (
      f"LOAD DATA LOCAL INFILE '{path_sql}' REPLACE INTO TABLE {self.table_name} "
      "CHARACTER SET utf8mb4 "
      "FIELDS TERMINATED BY '\\t' ESCAPED BY '' "
      "LINES TERMINATED BY '\\n' "
      f"({columns_sql}) SET {set_sql}"
    )
    try:
      cursor.execute(load_sql)
    except pymysql_err.OperationalError as exc:
      code = exc.args[0] if exc.args else None
      if code in (1148, 3948):
        raise RuntimeError(
          "LOAD DATA LOCAL INFILE is disabled. Ensure MySQL has local_infile=1 and "
          "the client enables local_infile."
        ) from exc
      raise
    self.handle.close()
    if not KEEP_LOAD_FILES:
      self.path.unlink(missing_ok=True)
    self.count = 0
    self._open()

  def close(self) -> None:
    if self.handle:
      self.handle.close()
    if self.path and self.path.exists() and not KEEP_LOAD_FILES:
      self.path.unlink(missing_ok=True)


def connect_without_db() -> pymysql.Connection:
  client_flag = CLIENT.LOCAL_FILES if BULK_MODE else 0
  return pymysql.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    charset="utf8mb4",
    autocommit=False,
    local_infile=BULK_MODE,
    client_flag=client_flag,
  )


def reconnect_with_db() -> pymysql.Connection:
  """Fast reconnect path: don't re-run schema DDL on reconnect."""
  conn = connect_without_db()
  conn.select_db(MYSQL_DATABASE)
  return conn


def ensure_schema(conn) -> None:
  ddl_path = Path(__file__).resolve().parent / "sql" / "001_nlk_ingest_tables.sql"
  sql = ddl_path.read_text()

  try:
    conn.select_db(MYSQL_DATABASE)
  except pymysql_err.OperationalError:
    with conn.cursor() as cursor:
      try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
        conn.select_db(MYSQL_DATABASE)
      except pymysql_err.MySQLError as exc:
        raise RuntimeError(
          f"Unable to select or create database '{MYSQL_DATABASE}'. "
          "Ensure it exists or use a user with CREATE DATABASE privileges."
        ) from exc

  with conn.cursor() as cursor:
    # NOTE: simple split is OK if your SQL file is only plain DDL statements (no procedures/triggers).
    for statement in sql.split(";"):
      stripped = statement.strip()
      if not stripped:
        continue
      lowered = stripped.lower()
      if lowered.startswith("create database") or lowered.startswith("use "):
        continue
      cursor.execute(statement)

    # Small schema guardrails (keep for compatibility)
    cursor.execute(
      """
      SELECT DATA_TYPE
      FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA=%s
        AND TABLE_NAME='nlk_biblio_docs'
        AND COLUMN_NAME='language_code'
      """,
      (MYSQL_DATABASE,),
    )
    row = cursor.fetchone()
    if row and row[0] and str(row[0]).lower() != "text":
      cursor.execute("ALTER TABLE nlk_biblio_docs MODIFY language_code TEXT NULL")

    cursor.execute(
      """
      SELECT DATA_TYPE
      FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA=%s
        AND TABLE_NAME='nlk_biblio_docs'
        AND COLUMN_NAME='volume'
      """,
      (MYSQL_DATABASE,),
    )
    row = cursor.fetchone()
    if row and row[0] and str(row[0]).lower() != "bigint":
      cursor.execute("ALTER TABLE nlk_biblio_docs MODIFY volume BIGINT NULL")

    cursor.execute(
      """
      SELECT DATA_TYPE
      FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA=%s
        AND TABLE_NAME='nlk_biblio_docs'
        AND COLUMN_NAME='publisher_name'
      """,
      (MYSQL_DATABASE,),
    )
    row = cursor.fetchone()
    if row and row[0] and str(row[0]).lower() != "text":
      cursor.execute("ALTER TABLE nlk_biblio_docs MODIFY publisher_name TEXT NULL")

    cursor.execute(
      """
      SELECT IS_NULLABLE, DATA_TYPE
      FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA=%s
        AND TABLE_NAME='nlk_biblio_docs'
        AND COLUMN_NAME='raw_json'
      """,
      (MYSQL_DATABASE,),
    )
    row = cursor.fetchone()
    if row and row[0] == "NO":
      if row[1] and str(row[1]).lower() == "json":
        cursor.execute("ALTER TABLE nlk_biblio_docs MODIFY raw_json JSON NULL")

  conn.commit()


def reset_tables(conn) -> None:
  with conn.cursor() as cursor:
    cursor.execute("TRUNCATE TABLE nlk_raw_nodes")
    cursor.execute("TRUNCATE TABLE nlk_biblio_docs")
  conn.commit()


def execute_chunked(cursor, sql: str, rows: List[Tuple[Any, ...]]) -> None:
  for idx in range(0, len(rows), CHUNK_SIZE):
    cursor.executemany(sql, rows[idx : idx + CHUNK_SIZE])


def upsert_raw(cursor, rows: List[Tuple[Any, ...]]) -> None:
  if not rows:
    return
  sql = """
        INSERT INTO nlk_raw_nodes
        (record_id, record_types, dataset, source_file, updated_at, updated_at_raw, raw_json, raw_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
          ON DUPLICATE KEY UPDATE
                             record_types=VALUES(record_types),
                             updated_at=VALUES(updated_at),
                             updated_at_raw=VALUES(updated_at_raw),
                             raw_json=VALUES(raw_json),
                             raw_hash=VALUES(raw_hash) \
        """
  execute_chunked(cursor, sql, rows)


def upsert_biblio(cursor, rows: List[Tuple[Any, ...]]) -> None:
  if not rows:
    return
  sql = """
        INSERT INTO nlk_biblio_docs
        (record_id, dataset, source_file, title, title_en, authors, authors_text, publisher_name,
         issued_year, language_code, volume, edition_labels, identifiers, updated_at, updated_at_raw, raw_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
          ON DUPLICATE KEY UPDATE
                             dataset=VALUES(dataset),
                             source_file=VALUES(source_file),
                             title=VALUES(title),
                             title_en=VALUES(title_en),
                             authors=VALUES(authors),
                             authors_text=VALUES(authors_text),
                             publisher_name=VALUES(publisher_name),
                             issued_year=VALUES(issued_year),
                             language_code=VALUES(language_code),
                             volume=VALUES(volume),
                             edition_labels=VALUES(edition_labels),
                             identifiers=VALUES(identifiers),
                             updated_at=VALUES(updated_at),
                             updated_at_raw=VALUES(updated_at_raw),
                             raw_json=VALUES(raw_json) \
        """
  execute_chunked(cursor, sql, rows)


def apply_ingest_session_settings(conn: pymysql.Connection) -> None:
  """Lightweight per-session settings for faster bulk ingest."""
  with conn.cursor() as cursor:
    if BULK_MODE:
      global LOCAL_INFILE_WARNED
      try:
        cursor.execute("SET SESSION local_infile=1")
      except pymysql_err.OperationalError as exc:
        code = exc.args[0] if exc.args else None
        if code == 1229:
          if not LOCAL_INFILE_WARNED:
            print(
              "[mysql] local_infile is GLOBAL-only on this server. "
              "Ensure MySQL has local_infile=1 enabled."
            )
            LOCAL_INFILE_WARNED = True
        else:
          raise
    if DISABLE_FK_CHECKS:
      cursor.execute("SET SESSION foreign_key_checks=0")
    if DISABLE_UNIQUE_CHECKS:
      cursor.execute("SET SESSION unique_checks=0")
    # Reduce binary log pressure if you *know* this is local and binlog is irrelevant.
    # DO NOT enable this in environments that rely on replication/CDC.
    # cursor.execute("SET SESSION sql_log_bin=0")
  conn.commit()


def process_file(conn, checkpoint_store: CheckpointStore, file_path: Path) -> None:
  dataset = dataset_name(file_path)
  dataset_lower = dataset.lower()
  format_type = detect_format(file_path)

  checkpoint = checkpoint_store.load(file_path)
  start_offset = int(checkpoint.get("offset", 0))
  start_index = int(checkpoint.get("graph_index", 0))

  raw_rows: List[Tuple[Any, ...]] = []
  biblio_rows: List[Tuple[Any, ...]] = []
  raw_loader = LoadDataBuffer("nlk_raw_nodes", RAW_COLUMNS) if BULK_MODE else None
  biblio_loader = LoadDataBuffer("nlk_biblio_docs", BIBLIO_COLUMNS) if BULK_MODE else None

  processed = 0
  last_offset = start_offset
  last_line = int(checkpoint.get("line", 0))
  last_index = start_index

  # Correct progress calculation (separate from flush timing)
  last_progress_time = time.time()
  last_progress_processed = 0

  def flush(latest_checkpoint: Dict[str, Any]) -> None:
    nonlocal raw_rows, biblio_rows, conn, raw_loader, biblio_loader
    attempts = 0
    backoff = RECONNECT_BACKOFF_BASE_SEC

    while True:
      try:
        with conn.cursor() as cursor:
          if BULK_MODE and raw_loader and biblio_loader:
            raw_loader.flush(cursor)
            biblio_loader.flush(cursor)
          else:
            upsert_raw(cursor, raw_rows)
            upsert_biblio(cursor, biblio_rows)
        conn.commit()

        if latest_checkpoint:
          checkpoint_store.save(file_path, latest_checkpoint)

        raw_rows = []
        biblio_rows = []
        return

      except pymysql_err.OperationalError as exc:
        code = exc.args[0] if exc.args else None

        # 2006: MySQL server has gone away
        # 2013: Lost connection to MySQL server during query
        # 1598: Server stopped (e.g., ABORT_SERVER on binlog sync failure)
        if code in (2006, 2013, 1598) and attempts < MAX_RECONNECT_RETRIES:
          attempts += 1
          print(
            f"[mysql] commit failed (code={code}); reconnecting and retrying batch "
            f"(attempt {attempts}/{MAX_RECONNECT_RETRIES})..."
          )
          try:
            conn.close()
          except pymysql_err.MySQLError:
            pass

          time.sleep(backoff)
          backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX_SEC)

          conn = reconnect_with_db()
          apply_ingest_session_settings(conn)
          continue

        if code == 1153:
          print(
            "[mysql] max_allowed_packet exceeded. "
            "Reduce MYSQL_CHUNK_SIZE or increase MySQL max_allowed_packet."
          )
        raise

  # Apply per-session settings once per file (helps bulk ingest speed)
  apply_ingest_session_settings(conn)

  if format_type == "ndjson":
    for line_number, offset, node in iter_ndjson(file_path, start_offset):
      record_id = extract_record_id(node)
      if not record_id:
        continue

      updated_at, updated_raw = extract_updated_at(node)
      raw_json = json.dumps(node, **DUMPS_KWARGS)
      raw_hash = compute_raw_hash(record_id, raw_json)
      record_types = json.dumps(extract_types(node), **DUMPS_KWARGS)

      raw_row = (
        record_id,
        record_types,
        dataset,
        file_path.name,
        updated_at,
        updated_raw,
        raw_json,
        raw_hash,
      )
      if BULK_MODE and raw_loader:
        raw_loader.write_row(raw_row)
      else:
        raw_rows.append(raw_row)

      if dataset_lower in BIBLIO_DATASETS:
        title_ko, title_en = extract_title(node)
        contributors = extract_contributors(node)
        author_names = []
        for entry in contributors:
          name = entry.get("name_ko") or entry.get("name_en")
          if name:
            author_names.append(name)

        raw_json_biblio = raw_json if STORE_BIBLIO_RAW else None
        biblio_row = (
          record_id,
          dataset,
          file_path.name,
          title_ko,
          title_en,
          json.dumps(contributors, **DUMPS_KWARGS),
          "; ".join(author_names) if author_names else None,
          extract_publisher(node),
          extract_issued_year(node),
          extract_language(node),
          extract_volume(node),
          json.dumps(extract_edition_labels(node), **DUMPS_KWARGS),
          json.dumps(extract_identifiers(node), **DUMPS_KWARGS),
          updated_at,
          updated_raw,
          raw_json_biblio,
        )
        if BULK_MODE and biblio_loader:
          biblio_loader.write_row(biblio_row)
        else:
          biblio_rows.append(biblio_row)

      processed += 1
      last_offset = offset
      last_line = line_number

      if not BULK_MODE and processed % BATCH_SIZE == 0:
        flush({"offset": last_offset, "line": last_line})

      if BULK_MODE and (
        (raw_loader and raw_loader.count >= LOAD_BATCH_ROWS)
        or (biblio_loader and biblio_loader.count >= LOAD_BATCH_ROWS)
      ):
        flush({"offset": last_offset, "line": last_line})

      if processed % PROGRESS_EVERY == 0:
        now = time.time()
        elapsed = now - last_progress_time
        delta = processed - last_progress_processed
        rate = delta / elapsed if elapsed > 0 else 0.0
        print(f"[mysql] {file_path.name}: {processed} records ({rate:.1f}/s)")
        last_progress_time = now
        last_progress_processed = processed

  else:
    for index, node in iter_jsonld_graph(file_path, start_index):
      record_id = extract_record_id(node)
      if not record_id:
        continue

      updated_at, updated_raw = extract_updated_at(node)
      raw_json = json.dumps(node, **DUMPS_KWARGS)
      raw_hash = compute_raw_hash(record_id, raw_json)
      record_types = json.dumps(extract_types(node), **DUMPS_KWARGS)

      raw_row = (
        record_id,
        record_types,
        dataset,
        file_path.name,
        updated_at,
        updated_raw,
        raw_json,
        raw_hash,
      )
      if BULK_MODE and raw_loader:
        raw_loader.write_row(raw_row)
      else:
        raw_rows.append(raw_row)

      if dataset_lower in BIBLIO_DATASETS:
        title_ko, title_en = extract_title(node)
        contributors = extract_contributors(node)
        author_names = []
        for entry in contributors:
          name = entry.get("name_ko") or entry.get("name_en")
          if name:
            author_names.append(name)

        raw_json_biblio = raw_json if STORE_BIBLIO_RAW else None
        biblio_row = (
          record_id,
          dataset,
          file_path.name,
          title_ko,
          title_en,
          json.dumps(contributors, **DUMPS_KWARGS),
          "; ".join(author_names) if author_names else None,
          extract_publisher(node),
          extract_issued_year(node),
          extract_language(node),
          extract_volume(node),
          json.dumps(extract_edition_labels(node), **DUMPS_KWARGS),
          json.dumps(extract_identifiers(node), **DUMPS_KWARGS),
          updated_at,
          updated_raw,
          raw_json_biblio,
        )
        if BULK_MODE and biblio_loader:
          biblio_loader.write_row(biblio_row)
        else:
          biblio_rows.append(biblio_row)

      processed += 1
      last_index = index

      if not BULK_MODE and processed % BATCH_SIZE == 0:
        flush({"graph_index": last_index})

      if BULK_MODE and (
        (raw_loader and raw_loader.count >= LOAD_BATCH_ROWS)
        or (biblio_loader and biblio_loader.count >= LOAD_BATCH_ROWS)
      ):
        flush({"graph_index": last_index})

      if processed % PROGRESS_EVERY == 0:
        now = time.time()
        elapsed = now - last_progress_time
        delta = processed - last_progress_processed
        rate = delta / elapsed if elapsed > 0 else 0.0
        print(f"[mysql] {file_path.name}: {processed} records ({rate:.1f}/s)")
        last_progress_time = now
        last_progress_processed = processed

  # Final flush
  has_pending = bool(raw_rows or biblio_rows)
  if BULK_MODE and raw_loader and biblio_loader:
    has_pending = raw_loader.count > 0 or biblio_loader.count > 0

  if has_pending:
    if format_type == "ndjson":
      flush({"offset": last_offset, "line": last_line})
    else:
      flush({"graph_index": last_index})

  if BULK_MODE:
    if raw_loader:
      raw_loader.close()
    if biblio_loader:
      biblio_loader.close()


def main() -> int:
  if not raw_dir().exists():
    print(f"Raw data directory not found: {raw_dir()}")
    return 1

  checkpoint_store = CheckpointStore(checkpoints_dir(), "mysql")
  if RESET:
    checkpoint_store.clear()

  conn = connect_without_db()
  ensure_schema(conn)
  if RESET:
    reset_tables(conn)

  files = iter_input_files()
  if not files:
    print(f"No input files found in {raw_dir()}")
    return 1

  for file_path in files:
    print(f"[mysql] ingesting {file_path.name}")
    process_file(conn, checkpoint_store, file_path)

  conn.close()
  print("[mysql] ingestion complete")
  return 0


if __name__ == "__main__":
  sys.exit(main())
