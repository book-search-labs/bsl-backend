import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]


def _coerce_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    return default


def _coerce_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _coerce_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str

    os_url: str
    doc_alias: str
    doc_read_alias: str
    index_prefix: str
    mapping_path: Path
    delete_existing: bool

    batch_size: int
    bulk_size: int
    retry_max: int
    retry_backoff_sec: float
    timeout_sec: int
    max_failures: int
    bulk_delay_sec: float

    health_check_interval_sec: int
    health_sleep_yellow_sec: int
    health_sleep_red_sec: int

    refresh_interval_bulk: str
    refresh_interval_post: str

    job_poll_interval_sec: int

    @staticmethod
    def from_env() -> "Settings":
        mapping = os.environ.get("BOOKS_DOC_MAPPING", str(ROOT_DIR / "infra/opensearch/books_doc_v1.mapping.json"))
        mapping_path = Path(mapping)
        if not mapping_path.is_absolute():
            mapping_path = ROOT_DIR / mapping_path
        return Settings(
            mysql_host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            mysql_port=_coerce_int(os.environ.get("MYSQL_PORT"), 3306),
            mysql_user=os.environ.get("MYSQL_USER", "bsl"),
            mysql_password=os.environ.get("MYSQL_PASSWORD", "bsl"),
            mysql_database=os.environ.get("MYSQL_DATABASE", "bsl"),
            os_url=os.environ.get("OS_URL", "http://localhost:9200"),
            doc_alias=os.environ.get("BOOKS_DOC_ALIAS", "books_doc_write"),
            doc_read_alias=os.environ.get("BOOKS_DOC_READ_ALIAS", "books_doc_read"),
            index_prefix=os.environ.get("BOOKS_DOC_INDEX_PREFIX", "books_doc_v1_local"),
            mapping_path=mapping_path,
            delete_existing=_coerce_bool(os.environ.get("DELETE_EXISTING"), False),
            batch_size=_coerce_int(os.environ.get("MYSQL_BATCH_SIZE"), 1000),
            bulk_size=_coerce_int(os.environ.get("OS_BULK_SIZE"), 1000),
            retry_max=_coerce_int(os.environ.get("OS_RETRY_MAX"), 3),
            retry_backoff_sec=_coerce_float(os.environ.get("OS_RETRY_BACKOFF_SEC"), 1.0),
            timeout_sec=_coerce_int(os.environ.get("OS_TIMEOUT_SEC"), 30),
            max_failures=_coerce_int(os.environ.get("REINDEX_MAX_FAILURES"), 1000),
            bulk_delay_sec=_coerce_float(os.environ.get("REINDEX_BULK_DELAY_SEC"), 0.0),
            health_check_interval_sec=_coerce_int(os.environ.get("OS_HEALTH_CHECK_INTERVAL_SEC"), 10),
            health_sleep_yellow_sec=_coerce_int(os.environ.get("OS_HEALTH_SLEEP_YELLOW_SEC"), 1),
            health_sleep_red_sec=_coerce_int(os.environ.get("OS_HEALTH_SLEEP_RED_SEC"), 5),
            refresh_interval_bulk=os.environ.get("OS_REFRESH_INTERVAL_BULK", "-1"),
            refresh_interval_post=os.environ.get("OS_REFRESH_INTERVAL_POST", "1s"),
            job_poll_interval_sec=_coerce_int(os.environ.get("JOB_POLL_INTERVAL_SEC"), 2),
        )

    def override(self, params: Optional[Dict[str, Any]]) -> "Settings":
        if not params:
            return self

        mapping_path = self.mapping_path
        if isinstance(params.get("mapping_path"), str):
            path = Path(params["mapping_path"])
            mapping_path = path if path.is_absolute() else ROOT_DIR / path

        return Settings(
            mysql_host=params.get("mysql_host", self.mysql_host),
            mysql_port=int(params.get("mysql_port", self.mysql_port)),
            mysql_user=params.get("mysql_user", self.mysql_user),
            mysql_password=params.get("mysql_password", self.mysql_password),
            mysql_database=params.get("mysql_database", self.mysql_database),
            os_url=params.get("os_url", self.os_url),
            doc_alias=params.get("doc_alias", self.doc_alias),
            doc_read_alias=params.get("doc_read_alias", self.doc_read_alias),
            index_prefix=params.get("index_prefix", self.index_prefix),
            mapping_path=mapping_path,
            delete_existing=bool(params.get("delete_existing", self.delete_existing)),
            batch_size=int(params.get("batch_size", self.batch_size)),
            bulk_size=int(params.get("bulk_size", self.bulk_size)),
            retry_max=int(params.get("retry_max", self.retry_max)),
            retry_backoff_sec=float(params.get("retry_backoff_sec", self.retry_backoff_sec)),
            timeout_sec=int(params.get("timeout_sec", self.timeout_sec)),
            max_failures=int(params.get("max_failures", self.max_failures)),
            bulk_delay_sec=float(params.get("bulk_delay_sec", self.bulk_delay_sec)),
            health_check_interval_sec=int(params.get("health_check_interval_sec", self.health_check_interval_sec)),
            health_sleep_yellow_sec=int(params.get("health_sleep_yellow_sec", self.health_sleep_yellow_sec)),
            health_sleep_red_sec=int(params.get("health_sleep_red_sec", self.health_sleep_red_sec)),
            refresh_interval_bulk=str(params.get("refresh_interval_bulk", self.refresh_interval_bulk)),
            refresh_interval_post=str(params.get("refresh_interval_post", self.refresh_interval_post)),
            job_poll_interval_sec=int(params.get("job_poll_interval_sec", self.job_poll_interval_sec)),
        )
