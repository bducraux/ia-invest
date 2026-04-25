"""Per-file extraction cache.

Caches the raw output of an extractor (records + errors) keyed by SHA-256
of the source file plus the extractor's ``source_type`` and
``EXTRACTOR_VERSION``. Lets re-imports skip slow parsing (e.g. PDF text
extraction) when the file content is unchanged and the extractor has not
been bumped.

Cache files live under ``<portfolio_dir>/.cache/extractions/<sha256>.json``
and are safe to delete at any time. The cache is opt-in: extractors must
set ``ENABLE_EXTRACTION_CACHE = True`` (and bump ``EXTRACTOR_VERSION`` on
parser changes) to participate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import structlog

from extractors.base import BaseExtractor, ExtractionResult

log = structlog.get_logger()

_CACHE_SCHEMA_VERSION = 1
_CACHE_DIRNAME = ".cache"
_CACHE_SUBDIR = "extractions"
_ALIASES_SUBDIR = "aliases"
_PORTFOLIO_SUBFOLDERS = {"inbox", "staging", "processed", "rejected"}


def file_sha256(file_path: Path) -> str:
    """Return SHA-256 hex digest of the file contents."""
    h = hashlib.sha256()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _portfolio_dir_for(file_path: Path) -> Path | None:
    """Resolve ``<portfolio_dir>`` from a file inside ``inbox/staging/...``."""
    parent = file_path.parent
    if parent.name in _PORTFOLIO_SUBFOLDERS:
        return parent.parent
    return None


def _cache_path(file_path: Path, file_hash: str) -> Path | None:
    pd = _portfolio_dir_for(file_path)
    if pd is None:
        return None
    return pd / _CACHE_DIRNAME / _CACHE_SUBDIR / f"{file_hash}.json"


def _is_enabled(extractor: BaseExtractor) -> bool:
    return bool(getattr(extractor, "ENABLE_EXTRACTION_CACHE", False))


def _extractor_version(extractor: BaseExtractor) -> int:
    return int(getattr(extractor, "EXTRACTOR_VERSION", 1))


def load_cached_extraction(
    file_path: Path,
    extractor: BaseExtractor,
    *,
    file_hash: str | None = None,
) -> ExtractionResult | None:
    """Return a cached ``ExtractionResult`` if it matches file + extractor version.

    Returns ``None`` on any kind of miss (disabled extractor, file outside a
    portfolio tree, missing/corrupt cache file, version mismatch).
    """
    if not _is_enabled(extractor):
        return None
    file_hash = file_hash or file_sha256(file_path)
    cache_file = _cache_path(file_path, file_hash)
    if cache_file is None or not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(
            "extraction_cache_corrupt",
            path=str(cache_file),
            error=str(exc),
        )
        return None
    if (
        payload.get("schema_version") != _CACHE_SCHEMA_VERSION
        or payload.get("source_type") != extractor.source_type
        or payload.get("extractor_version") != _extractor_version(extractor)
        or payload.get("file_hash") != file_hash
    ):
        return None
    return ExtractionResult(
        records=list(payload.get("records", [])),
        errors=list(payload.get("errors", [])),
        source_type=payload.get("source_type", extractor.source_type),
    )


def save_cached_extraction(
    file_path: Path,
    extractor: BaseExtractor,
    result: ExtractionResult,
    *,
    file_hash: str | None = None,
) -> None:
    """Persist ``result`` to the per-file cache (no-op if extractor opts out).

    Decimals/dates and other non-JSON-native values are serialised via
    ``str()`` — the same wire format the normalisers already accept from
    CSV-derived dicts.
    """
    if not _is_enabled(extractor):
        return
    file_hash = file_hash or file_sha256(file_path)
    cache_file = _cache_path(file_path, file_hash)
    if cache_file is None:
        return
    payload: dict[str, Any] = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "source_type": extractor.source_type,
        "extractor_version": _extractor_version(extractor),
        "file_hash": file_hash,
        "file_name": file_path.name,
        "records": result.records,
        "errors": result.errors,
    }
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning(
            "extraction_cache_write_failed",
            path=str(cache_file),
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Sidecar cache for harvested aliases (Avenue/Apex pre-pass).
# ---------------------------------------------------------------------------


def _aliases_cache_path(file_path: Path, file_hash: str) -> Path | None:
    pd = _portfolio_dir_for(file_path)
    if pd is None:
        return None
    return pd / _CACHE_DIRNAME / _ALIASES_SUBDIR / f"{file_hash}.json"


def load_cached_aliases(
    file_path: Path,
    extractor: BaseExtractor,
    *,
    file_hash: str | None = None,
) -> list[dict[str, Any]] | None:
    """Return cached harvested aliases for the file, or ``None`` on miss.

    Each list element is ``{"name": str, "symbol": str, "cusip": str | None}``.
    """
    if not _is_enabled(extractor):
        return None
    file_hash = file_hash or file_sha256(file_path)
    cache_file = _aliases_cache_path(file_path, file_hash)
    if cache_file is None or not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(
            "aliases_cache_corrupt",
            path=str(cache_file),
            error=str(exc),
        )
        return None
    if (
        payload.get("schema_version") != _CACHE_SCHEMA_VERSION
        or payload.get("source_type") != extractor.source_type
        or payload.get("extractor_version") != _extractor_version(extractor)
        or payload.get("file_hash") != file_hash
    ):
        return None
    aliases = payload.get("aliases")
    if not isinstance(aliases, list):
        return None
    return aliases


def save_cached_aliases(
    file_path: Path,
    extractor: BaseExtractor,
    aliases: list[dict[str, Any]],
    *,
    file_hash: str | None = None,
) -> None:
    if not _is_enabled(extractor):
        return
    file_hash = file_hash or file_sha256(file_path)
    cache_file = _aliases_cache_path(file_path, file_hash)
    if cache_file is None:
        return
    payload = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "source_type": extractor.source_type,
        "extractor_version": _extractor_version(extractor),
        "file_hash": file_hash,
        "file_name": file_path.name,
        "aliases": aliases,
    }
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning(
            "aliases_cache_write_failed",
            path=str(cache_file),
            error=str(exc),
        )
