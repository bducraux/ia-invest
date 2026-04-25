"""Tests for the per-file extraction cache."""

from __future__ import annotations

import json
from pathlib import Path

from extractors.base import BaseExtractor, ExtractionResult
from extractors.cache import (
    file_sha256,
    load_cached_extraction,
    save_cached_extraction,
)


class _DummyExtractor(BaseExtractor):
    source_type = "dummy"
    ENABLE_EXTRACTION_CACHE = True
    EXTRACTOR_VERSION = 1

    def can_handle(self, file_path: Path) -> bool:  # pragma: no cover
        return True

    def extract(self, file_path: Path) -> ExtractionResult:  # pragma: no cover
        return ExtractionResult(records=[], errors=[], source_type=self.source_type)


class _DisabledExtractor(_DummyExtractor):
    source_type = "dummy_off"
    ENABLE_EXTRACTION_CACHE = False


def _make_portfolio_file(tmp_path: Path, content: bytes = b"hello") -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    f = inbox / "sample.pdf"
    f.write_bytes(content)
    return f


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    file_path = _make_portfolio_file(tmp_path)
    assert load_cached_extraction(file_path, _DummyExtractor()) is None


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    file_path = _make_portfolio_file(tmp_path)
    extractor = _DummyExtractor()
    result = ExtractionResult(
        records=[{"asset_code": "BTC", "qty": "1.5"}],
        errors=[{"message": "skipped"}],
        source_type=extractor.source_type,
    )

    save_cached_extraction(file_path, extractor, result)
    cached = load_cached_extraction(file_path, extractor)

    assert cached is not None
    assert cached.records == result.records
    assert cached.errors == result.errors
    assert cached.source_type == extractor.source_type

    cache_dir = tmp_path / ".cache" / "extractions"
    assert cache_dir.is_dir()
    files = list(cache_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.endswith(".json")


def test_version_bump_invalidates(tmp_path: Path) -> None:
    file_path = _make_portfolio_file(tmp_path)
    extractor_v1 = _DummyExtractor()
    save_cached_extraction(
        file_path,
        extractor_v1,
        ExtractionResult(records=[{"x": 1}], source_type="dummy"),
    )

    class _DummyV2(_DummyExtractor):
        EXTRACTOR_VERSION = 2

    assert load_cached_extraction(file_path, _DummyV2()) is None
    # Old version still hits its own cache.
    assert load_cached_extraction(file_path, extractor_v1) is not None


def test_file_change_invalidates(tmp_path: Path) -> None:
    file_path = _make_portfolio_file(tmp_path, b"hello")
    extractor = _DummyExtractor()
    save_cached_extraction(
        file_path, extractor, ExtractionResult(records=[{"a": 1}])
    )
    assert load_cached_extraction(file_path, extractor) is not None

    file_path.write_bytes(b"world")
    assert load_cached_extraction(file_path, extractor) is None


def test_disabled_extractor_skips_cache(tmp_path: Path) -> None:
    file_path = _make_portfolio_file(tmp_path)
    extractor = _DisabledExtractor()
    save_cached_extraction(
        file_path, extractor, ExtractionResult(records=[{"x": 1}])
    )
    cache_dir = tmp_path / ".cache"
    assert not cache_dir.exists()
    assert load_cached_extraction(file_path, extractor) is None


def test_file_outside_portfolio_tree_is_noop(tmp_path: Path) -> None:
    # File NOT under inbox/staging/processed → cache resolves to None and is skipped.
    f = tmp_path / "loose.pdf"
    f.write_bytes(b"x")
    save_cached_extraction(
        f, _DummyExtractor(), ExtractionResult(records=[{"x": 1}])
    )
    assert load_cached_extraction(f, _DummyExtractor()) is None
    assert not (tmp_path / ".cache").exists()


def test_cross_subfolder_cache_hits(tmp_path: Path) -> None:
    """File moved inbox→processed must still hit the same cache (same hash)."""
    file_path = _make_portfolio_file(tmp_path, b"payload")
    extractor = _DummyExtractor()
    save_cached_extraction(
        file_path, extractor, ExtractionResult(records=[{"k": "v"}])
    )

    processed = tmp_path / "processed"
    processed.mkdir()
    moved = processed / file_path.name
    file_path.rename(moved)

    cached = load_cached_extraction(moved, extractor)
    assert cached is not None
    assert cached.records == [{"k": "v"}]


def test_corrupt_cache_returns_none(tmp_path: Path) -> None:
    file_path = _make_portfolio_file(tmp_path)
    extractor = _DummyExtractor()
    digest = file_sha256(file_path)
    cache_file = tmp_path / ".cache" / "extractions" / f"{digest}.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("{not json", encoding="utf-8")
    assert load_cached_extraction(file_path, extractor) is None


def test_serialises_non_native_types(tmp_path: Path) -> None:
    """Decimals/dates etc. must round-trip via str() without crashing."""
    from datetime import date
    from decimal import Decimal

    file_path = _make_portfolio_file(tmp_path)
    extractor = _DummyExtractor()
    save_cached_extraction(
        file_path,
        extractor,
        ExtractionResult(
            records=[{"qty": Decimal("1.23"), "when": date(2026, 4, 24)}]
        ),
    )
    cached = load_cached_extraction(file_path, extractor)
    assert cached is not None
    # str()-coerced on save; normalisers handle string→Decimal/date downstream.
    assert cached.records == [{"qty": "1.23", "when": "2026-04-24"}]
    # Sanity: file is valid JSON.
    cache_dir = tmp_path / ".cache" / "extractions"
    payload = json.loads(next(cache_dir.iterdir()).read_text())
    assert payload["schema_version"] == 1
    assert payload["source_type"] == "dummy"
