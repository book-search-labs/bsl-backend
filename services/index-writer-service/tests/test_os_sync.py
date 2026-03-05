from datetime import datetime

from app.config import Settings
from app.os_sync import EVENT_DELETE, EVENT_UPSERT, OsSyncService


class FakeDb:
    def __init__(self):
        self.processed = set()
        self.outbox_events = []
        self.checkpoint = None
        self.delta_rows = []

    def is_event_processed(self, event_id, handler):
        return (event_id, handler) in self.processed

    def mark_event_processed(self, event_id, handler):
        self.processed.add((event_id, handler))

    def fetch_reconcile_checkpoint(self, checkpoint_name):
        return self.checkpoint

    def fetch_material_delta(self, last_updated_at, last_material_id, limit):
        return list(self.delta_rows)

    def insert_outbox_event(self, event_type, aggregate_type, aggregate_id, version, payload):
        self.outbox_events.append(
            {
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "version": version,
                "payload": payload,
            }
        )
        return True

    def upsert_reconcile_checkpoint(self, checkpoint_name, last_updated_at, last_material_id):
        self.checkpoint = {
            "checkpoint_name": checkpoint_name,
            "last_updated_at": last_updated_at,
            "last_material_id": last_material_id,
        }

    def fetch_os_sync_lag_seconds(self):
        return 0

    def fetch_recent_os_sync_failures(self, limit=20):
        return []

    def connect(self):
        raise RuntimeError("not used in this unit test")


class FakeClient:
    pass


class FakeRecord:
    def __init__(self, key, value):
        self.key = key
        self.value = value



def build_settings() -> Settings:
    settings = Settings.from_env()
    settings.os_sync_enabled = True
    settings.os_sync_handler = "test-handler"
    settings.os_sync_retry_max = 1
    settings.os_sync_retry_backoff_sec = 0
    settings.os_sync_reconcile_batch_size = 100
    settings.os_sync_reconcile_max_enqueue = 100
    settings.os_sync_reconcile_checkpoint_name = "test-checkpoint"
    return settings



def test_consumer_idempotency_with_processed_event_guard():
    settings = build_settings()
    db = FakeDb()
    service = OsSyncService(settings, db, FakeClient())

    calls = []

    def fake_upsert(material_id, version):
        calls.append((material_id, version))

    service._upsert_material = fake_upsert  # type: ignore[method-assign]

    envelope = {
        "schema_version": "v1",
        "event_id": "1001",
        "event_type": EVENT_UPSERT,
        "aggregate_type": "material",
        "aggregate_id": "nlk:CM000000001",
        "payload": {"version": "v1", "material_id": "nlk:CM000000001"},
    }
    record = FakeRecord("nlk:CM000000001", envelope)

    service._process_record(record, producer=None)
    service._process_record(record, producer=None)

    assert len(calls) == 1
    assert service.metrics.skipped_duplicate_total == 1



def test_reconcile_requeues_upsert_and_delete():
    settings = build_settings()
    db = FakeDb()
    service = OsSyncService(settings, db, FakeClient())

    db.delta_rows = [
        {
            "material_id": "m-upsert",
            "updated_at": datetime(2026, 3, 5, 10, 0, 0),
            "deleted_at": None,
        },
        {
            "material_id": "m-delete",
            "updated_at": datetime(2026, 3, 5, 10, 1, 0),
            "deleted_at": datetime(2026, 3, 5, 10, 1, 30),
        },
    ]

    service._is_drifted = lambda material_id, updated_at: material_id == "m-upsert"  # type: ignore[method-assign]

    result = service.run_reconcile_once()

    assert result == {"scanned": 2, "requeued": 2}
    assert [event["event_type"] for event in db.outbox_events] == [EVENT_UPSERT, EVENT_DELETE]
    assert db.checkpoint is not None
