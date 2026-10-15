import hashlib
from urllib.error import HTTPError

import pytest
from pydantic import ValidationError

from nfl_prediction.data import audit
from nfl_prediction.data.manifests import SourceManifest


def test_prefix_hash_and_rows_do_not_claim_full_coverage() -> None:
    body = b'season,week,note\n2026,1,"a,b"\n2026,2,c\n2026,3,d\n2026,4,"partial'
    summary = audit.summarize_sample(body, ("season", "missing"), complete=False)
    assert summary["rows_examined"] == 3
    assert summary["sha256"] == hashlib.sha256(body).hexdigest()
    assert summary["checksum_scope"] == "sample_prefix"
    assert summary["coverage"] == "first_three_rows_only"
    assert summary["missing_required_columns"] == ["missing"]


def test_ignored_range_is_still_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, count):
            assert count == 12
            return b"x" * count

    monkeypatch.setattr(audit, "urlopen", lambda *args, **kwargs: Response())
    body, _ = audit.read_bounded("https://example.com/data.csv", 12, prefix=True)
    assert len(body) == 12


def test_unquoted_prefix_tail_is_not_a_complete_record() -> None:
    _, rows = audit.parse_csv(b"season,week\n2026,1\n2026,2", complete=False)
    assert rows == [{"season": "2026", "week": "1"}]


def test_release_failure_is_unknown_not_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args, **kwargs):
        raise HTTPError("https://example.com", 403, "Rate limited", {}, None)

    monkeypatch.setattr(audit, "read_bounded", denied)
    monkeypatch.setattr(audit, "audit_schedule", lambda _: {"status": "probe_error"})
    report = audit.run_audit(2026, 1)
    assert len(report["datasets"]) == 14
    assert all(entry["status"] == "metadata_error" for entry in report["datasets"])


def manifest_fields() -> dict:
    return {
        "dataset": "injuries",
        "season": 2026,
        "source_url": "https://example.com/injuries.csv",
        "retrieved_at": "2026-10-15T01:00:00Z",
        "sha256": "a" * 64,
        "checksum_scope": "sample_prefix",
        "byte_count": 100,
        "source_schema_version": "injuries/2",
        "coverage": "sample_only",
        "attribution_url": "https://example.com/credits",
        "redistribution_status": "review_required",
    }


def test_retrieval_does_not_imply_historical_availability() -> None:
    manifest = SourceManifest(**manifest_fields())
    assert manifest.available_at is None
    assert manifest.source_published_at is None
    with pytest.raises(ValidationError, match="availability_evidence"):
        SourceManifest(**manifest_fields(), available_at="2026-10-14T01:00:00Z")


def test_naive_timestamp_and_prefix_season_claim_are_rejected() -> None:
    fields = manifest_fields()
    fields["retrieved_at"] = "2026-10-15T01:00:00"
    with pytest.raises(ValidationError):
        SourceManifest(**fields)
    fields = manifest_fields()
    fields["coverage"] = "season_validated"
    with pytest.raises(ValidationError, match="prefix checksum"):
        SourceManifest(**fields)
