import sqlite3
import time
from array import array
from typing import List, Optional


class EmbeddingCache:
    def get(self, text_hash: str, model: str) -> Optional[List[float]]:
        raise NotImplementedError

    def put(self, text_hash: str, model: str, vector: List[float]) -> None:
        raise NotImplementedError


class SqliteEmbeddingCache(EmbeddingCache):
    def __init__(self, path: str, ttl_sec: int = 0) -> None:
        self._path = path
        self._ttl_sec = max(0, ttl_sec)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS emb_cache (hash TEXT, model TEXT, dim INTEGER, vector BLOB, created_at INTEGER, PRIMARY KEY (hash, model))"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_cache_created ON emb_cache (created_at)")
        self._conn.commit()

    def get(self, text_hash: str, model: str) -> Optional[List[float]]:
        cursor = self._conn.execute(
            "SELECT dim, vector, created_at FROM emb_cache WHERE hash=? AND model=?",
            (text_hash, model),
        )
        row = cursor.fetchone()
        if not row:
            return None
        dim, blob, created_at = row
        if self._ttl_sec > 0:
            age = int(time.time()) - int(created_at)
            if age > self._ttl_sec:
                self._conn.execute(
                    "DELETE FROM emb_cache WHERE hash=? AND model=?",
                    (text_hash, model),
                )
                self._conn.commit()
                return None
        if blob is None:
            return None
        values = array("f")
        values.frombytes(blob)
        if dim and dim != len(values):
            return None
        return [float(v) for v in values]

    def put(self, text_hash: str, model: str, vector: List[float]) -> None:
        if not vector:
            return
        values = array("f", vector)
        payload = values.tobytes()
        now = int(time.time())
        self._conn.execute(
            "INSERT OR REPLACE INTO emb_cache (hash, model, dim, vector, created_at) VALUES (?, ?, ?, ?, ?)",
            (text_hash, model, len(vector), payload, now),
        )
        self._conn.commit()


class RedisEmbeddingCache(EmbeddingCache):
    def __init__(self, url: str, ttl_sec: int = 0) -> None:
        try:
            import redis  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("redis library not available") from exc
        self._ttl_sec = max(0, ttl_sec)
        self._client = redis.Redis.from_url(url)

    def get(self, text_hash: str, model: str) -> Optional[List[float]]:
        key = self._key(text_hash, model)
        payload = self._client.get(key)
        if payload is None:
            return None
        values = array("f")
        values.frombytes(payload)
        return [float(v) for v in values]

    def put(self, text_hash: str, model: str, vector: List[float]) -> None:
        if not vector:
            return
        values = array("f", vector)
        key = self._key(text_hash, model)
        if self._ttl_sec > 0:
            self._client.setex(key, self._ttl_sec, values.tobytes())
        else:
            self._client.set(key, values.tobytes())

    def _key(self, text_hash: str, model: str) -> str:
        return f"emb:{model}:{text_hash}"
