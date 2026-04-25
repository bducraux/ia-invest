"""Extractor for Avenue Securities monthly Apex Clearing PDF statements.

The Avenue Brazilian app exposes a downloadable PDF labeled
*"Extrato mensal de investimentos – Origem: Relatório Apex"*. These are
standard Apex Clearing Corporation monthly statements (English layout)
covering one calendar month per file.

V1 scope
--------
* Parses **PORTFOLIO SUMMARY** (`EQUITIES / OPTIONS` table) to learn the
  ``description → ticker`` mapping for the month and feed the persistent
  alias cache (:class:`storage.repository.avenue_aliases.AvenueAliasesRepository`).
* Parses **BUY / SELL TRANSACTIONS** (newer layout) and
  **TRADE SETTLEMENT ACCOUNT** (older 2021 layout) sections to emit
  ``buy`` and ``split_bonus`` operations.
* Skips dividends, interest, fees, taxes, journals — these are emitted
  as ``_unsupported`` records so the file is reported but not rejected.

Two layout variants seen
------------------------
Old (2021)::

    TRADE SETTLEMENT ACCOUNT
    TRANSACTION DATE  DATE  TYPE  DESCRIPTION                  QUANTITY    PRICE      DEBIT    CREDIT
    BOUGHT 04/30/21 05/04/21 C ALPHABET INC                    0.02124   2,355.11             50.02
    CLASS A COMMON STOCK
    CUSIP: 02079K305

New (2022+)::

    BUY / SELL TRANSACTIONS
    BOUGHT 11/15/23 C ALPHABET INC                              2.00078   $132.448            $265.00
    CLASS A COMMON STOCK
    CUSIP: 02079K305

Stock split (no price/gross)::

    BOUGHT 07/20/22 C ALPHABET INC                              0.40356
    CLASS A COMMON STOCK
    STK SPLIT ON 0.02124 SHS
    REC 07/01/22 PAY 07/15/22
    CUSIP: 02079K305
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import pdfplumber

from extractors.base import BaseExtractor, ExtractionResult

# ---------------------------------------------------------------------------
# Regex toolbox
# ---------------------------------------------------------------------------

# Matches a single MM/DD/YY date.
_DATE_RE = r"(?P<d>\d{2}/\d{2}/\d{2})"

# Main BOUGHT line — supports both layout variants:
#   New: "BOUGHT 11/15/23 C ALPHABET INC 2.00078 $132.448 $265.00"
#   Old: "BOUGHT 04/30/21 05/04/21 C ALPHABET INC 0.02124 2,355.11 50.02"
#   Split (no price): "BOUGHT 07/20/22 C ALPHABET INC 0.40356"
_BOUGHT_RE = re.compile(
    r"^BOUGHT\s+"
    r"(?P<trade_date>\d{2}/\d{2}/\d{2})"
    r"(?:\s+(?P<settle_date>\d{2}/\d{2}/\d{2}))?"
    r"\s+[A-Z]\s+"  # account type token (single letter, usually "C")
    r"(?P<rest>.+?)\s*$"
)

# CUSIP appears as the closing line of each BUY/SELL block.
_CUSIP_RE = re.compile(r"^\s*CUSIP:\s*(?P<cusip>[0-9A-Z]{6,9})\s*$")

# Split marker line.
_SPLIT_MARK_RE = re.compile(
    r"^\s*STK\s+SPLIT\s+ON\s+(?P<base>[\d,.]+)\s+SHS",
    re.IGNORECASE,
)

# Summary main line:
#   "ALPHABET INC GOOGL C 3.13706 $287.56 $902.09 ..."
#   "PEPSICO INC PEP C 2 155.29 ..."
# The ticker is the last 1-5 uppercase token immediately before " C " followed
# by a numeric quantity.
_SUMMARY_LINE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<symbol>[A-Z][A-Z0-9.]{0,4})\s+C\s+"
    r"(?P<qty>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b"
)

# Section header detection (case-insensitive comparisons done outside).
_SECTION_HEADERS = {
    "EQUITIES / OPTIONS": "summary",
    "EQUITIES / OPTIONS (CONTINUED)": "summary",
    "BUY / SELL TRANSACTIONS": "buy_sell",
    "TRADE SETTLEMENT ACCOUNT": "buy_sell",
    "DIVIDENDS AND INTEREST": "dividends",
    "DIVIDENDS AND INTEREST (CONTINUED)": "dividends",
    "FUNDS PAID AND RECEIVED": "funds",
    "INTEREST INCOME": "interest",
    "FEES": "fees",
    "MISCELLANEOUS": "misc",
}

# Lines that close any section (totals, page footers).
_END_OF_SECTION_RE = re.compile(
    r"^\s*Total\s+(Equities|Buy\s*/\s*Sell|Executed\s+Trades|Dividends|Funds|Interest|Fees|Cash)",
    re.IGNORECASE,
)

# Asset-name continuation lines in the SUMMARY (e.g. "CLASS A COMMON STOCK",
# "(THE)", "COMMON STOCK", "VANGUARD REAL ESTATE ETF").
_NAME_CONTINUATION_TOKENS = re.compile(r"^[A-Z(][A-Z0-9 .,&'/()\-]+$")


@dataclass
class _AliasResolver(Protocol):
    """Protocol for a persistent ``description → ticker`` cache."""

    def get(  # pragma: no cover - structural typing only
        self, portfolio_id: str, asset_name: str
    ) -> tuple[str, str | None] | None: ...

    def upsert(  # pragma: no cover - structural typing only
        self,
        portfolio_id: str,
        asset_name: str,
        asset_code: str,
        cusip: str | None = None,
        *,
        commit: bool = True,
    ) -> None: ...


@dataclass
class _SummaryEntry:
    name: str  # full normalized name (line + continuations joined)
    symbol: str


@dataclass
class _BuyBlock:
    trade_date: str  # YYYY-MM-DD
    settle_date: str | None  # YYYY-MM-DD or None
    description_lines: list[str]  # raw lines (used to derive name + flags)
    quantity: float
    unit_price_usd: float | None  # None for splits
    gross_value_usd: float | None  # None for splits
    cusip: str | None = None
    is_split: bool = False
    raw_lines: list[str] = field(default_factory=list)  # for diagnostics

    @property
    def joined_name(self) -> str:
        # Drop split marker / REC PAY / CUSIP lines from the description.
        parts: list[str] = []
        for line in self.description_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _CUSIP_RE.match(stripped):
                continue
            if _SPLIT_MARK_RE.match(stripped):
                continue
            if stripped.startswith("REC ") or stripped.startswith("PAY "):
                continue
            parts.append(stripped)
        return " ".join(parts).strip()


class AvenueApexPdfExtractor(BaseExtractor):
    """Parses Avenue/Apex monthly PDF statements into raw operation records."""

    source_type = "avenue_apex_pdf"
    ENABLE_EXTRACTION_CACHE = True
    EXTRACTOR_VERSION = 1

    def __init__(
        self,
        *,
        alias_repo: _AliasResolver | None = None,
        portfolio_id: str | None = None,
    ) -> None:
        self._alias_repo = alias_repo
        self._portfolio_id = portfolio_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".pdf":
            return False
        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return False
                first = pdf.pages[0].extract_text() or ""
        except Exception:
            return False
        upper = first.upper()
        return "APEX CLEARING" in upper and "ACCOUNT NUMBER" in upper

    def harvest_aliases(
        self, file_path: Path, *, file_hash: str | None = None
    ) -> dict[str, str]:
        """Read PORTFOLIO SUMMARY only; persist aliases. Returns ``{name: symbol}``.

        Used as a pre-pass before the main import to ensure that, when
        chronologically-early statements lack a summary (e.g. April 2021
        cash-only month), later statements have already populated the
        persistent cache so descriptions can still be resolved.

        Honours the per-file aliases cache (sidecar of the extraction cache)
        so unchanged PDFs do not need to be re-parsed on every run.
        """
        # Late import keeps the cache module optional for unit tests that
        # instantiate the extractor outside the import pipeline.
        from extractors.cache import load_cached_aliases, save_cached_aliases

        cached = load_cached_aliases(file_path, self, file_hash=file_hash)
        if cached is not None:
            if self._alias_repo is not None and self._portfolio_id:
                for entry in cached:
                    name = entry.get("name")
                    symbol = entry.get("symbol")
                    if not name or not symbol:
                        continue
                    self._alias_repo.upsert(
                        self._portfolio_id,
                        name,
                        symbol,
                        cusip=entry.get("cusip"),
                        commit=False,
                    )
            return {entry["name"]: entry["symbol"] for entry in cached if entry.get("name") and entry.get("symbol")}

        try:
            with pdfplumber.open(file_path) as pdf:
                pages_text = [page.extract_text() or "" for page in pdf.pages]
        except Exception:
            return {}
        summary_map = self._parse_summary("\n".join(pages_text).splitlines())
        aliases_payload: list[dict[str, Any]] = []
        for entry in summary_map.values():
            aliases_payload.append(
                {"name": entry.name, "symbol": entry.symbol, "cusip": None}
            )
            if self._alias_repo is not None and self._portfolio_id:
                self._alias_repo.upsert(
                    self._portfolio_id,
                    entry.name,
                    entry.symbol,
                    cusip=None,
                    commit=False,
                )
        save_cached_aliases(file_path, self, aliases_payload, file_hash=file_hash)
        return {key: entry.symbol for key, entry in summary_map.items()}

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)
        try:
            with pdfplumber.open(file_path) as pdf:
                pages_text = [page.extract_text() or "" for page in pdf.pages]
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": f"Could not read PDF file: {exc}",
                    "raw_data": {"file": file_path.name},
                }
            )
            return result

        full_text = "\n".join(pages_text)
        lines = full_text.splitlines()

        # Pass 1: build summary (description → symbol) for this month.
        summary_map = self._parse_summary(lines)

        # Update persistent cache with this month's findings.
        if self._alias_repo is not None and self._portfolio_id:
            for entry in summary_map.values():
                self._alias_repo.upsert(
                    self._portfolio_id,
                    entry.name,
                    entry.symbol,
                    cusip=None,
                    commit=False,
                )

        # Pass 2: parse BUY/SELL blocks and emit records.
        blocks = self._parse_buy_sell_blocks(lines)
        for block in blocks:
            try:
                record = self._block_to_record(
                    block,
                    file_name=file_path.name,
                    summary_map=summary_map,
                )
            except _UnresolvedNameError as exc:
                result.errors.append(
                    {
                        "row_index": None,
                        "error_type": "validation",
                        "message": str(exc),
                        "raw_data": {
                            "file": file_path.name,
                            "trade_date": block.trade_date,
                            "lines": block.raw_lines,
                        },
                    }
                )
                continue
            result.records.append(record)

        return result

    # ------------------------------------------------------------------
    # PORTFOLIO SUMMARY parser
    # ------------------------------------------------------------------

    def _parse_summary(self, lines: list[str]) -> dict[str, _SummaryEntry]:
        out: dict[str, _SummaryEntry] = {}
        in_section = False
        pending: _SummaryEntry | None = None

        for raw in lines:
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                continue

            upper = stripped.upper()
            if upper.startswith("EQUITIES / OPTIONS"):
                in_section = True
                pending = None
                continue
            if not in_section:
                continue
            if _END_OF_SECTION_RE.match(stripped):
                if pending is not None:
                    self._commit_summary(out, pending)
                    pending = None
                in_section = False
                continue
            # Skip page-flow noise inside the summary block.
            if any(
                key in upper
                for key in (
                    "SYMBOL/",
                    "DESCRIPTION CUSIP",
                    "PORTFOLIO SUMMARY",
                    "ACCOUNT NUMBER",
                    "PAGE ",
                    "BRUNO DUCRAUX",
                    "B. DUCRAUX",
                )
            ):
                continue

            match = _SUMMARY_LINE_RE.match(stripped)
            if match:
                if pending is not None:
                    self._commit_summary(out, pending)
                pending = _SummaryEntry(
                    name=_collapse_ws(match.group("name")),
                    symbol=match.group("symbol").upper(),
                )
                continue

            # Continuation line for the previous entry's name.
            if pending is not None and _NAME_CONTINUATION_TOKENS.match(stripped):
                pending = _SummaryEntry(
                    name=_collapse_ws(f"{pending.name} {stripped}"),
                    symbol=pending.symbol,
                )

        if pending is not None and in_section:
            self._commit_summary(out, pending)
        return out

    @staticmethod
    def _commit_summary(
        out: dict[str, _SummaryEntry], entry: _SummaryEntry
    ) -> None:
        key = _normalize_name(entry.name)
        if key:
            out[key] = entry

    # ------------------------------------------------------------------
    # BUY / SELL parser
    # ------------------------------------------------------------------

    def _parse_buy_sell_blocks(self, lines: list[str]) -> list[_BuyBlock]:
        blocks: list[_BuyBlock] = []
        in_section = False
        current: _BuyBlock | None = None

        for raw in lines:
            line = raw.rstrip()
            stripped = line.strip()
            upper = stripped.upper()

            if upper in ("BUY / SELL TRANSACTIONS", "TRADE SETTLEMENT ACCOUNT"):
                in_section = True
                continue

            # Other section headers terminate the buy/sell scan.
            if upper in _SECTION_HEADERS and _SECTION_HEADERS[upper] not in (
                "buy_sell",
            ):
                if current is not None:
                    blocks.append(current)
                    current = None
                in_section = False
                continue

            if not in_section:
                continue

            if not stripped:
                continue

            if _END_OF_SECTION_RE.match(stripped):
                if current is not None:
                    blocks.append(current)
                    current = None
                in_section = False
                continue

            if stripped.upper().startswith("BOUGHT "):
                if current is not None:
                    blocks.append(current)
                current = _start_buy_block(stripped)
                if current is not None:
                    current.raw_lines.append(stripped)
                continue

            if current is None:
                # Not inside a block — likely a SOLD line (not yet supported).
                continue

            current.raw_lines.append(stripped)

            cusip_match = _CUSIP_RE.match(stripped)
            if cusip_match:
                current.cusip = cusip_match.group("cusip")
                blocks.append(current)
                current = None
                continue

            if _SPLIT_MARK_RE.match(stripped):
                current.is_split = True
                current.description_lines.append(stripped)
                continue

            current.description_lines.append(stripped)

        if current is not None:
            blocks.append(current)
        return blocks

    # ------------------------------------------------------------------
    # Block → record
    # ------------------------------------------------------------------

    def _block_to_record(
        self,
        block: _BuyBlock,
        *,
        file_name: str,
        summary_map: dict[str, _SummaryEntry],
    ) -> dict[str, Any]:
        full_name = block.joined_name
        normalized = _normalize_name(full_name)

        symbol = self._resolve_symbol(normalized, summary_map, block.cusip)
        if symbol is None:
            raise _UnresolvedNameError(
                f"Could not resolve Avenue/Apex ticker for description "
                f"{full_name!r} (cusip={block.cusip})"
            )

        # Persist the alias for future months. Always upsert so we attach
        # CUSIP when we learn it from the BUY/SELL section.
        if self._alias_repo is not None and self._portfolio_id:
            self._alias_repo.upsert(
                self._portfolio_id,
                full_name,
                symbol,
                cusip=block.cusip,
                commit=False,
            )

        operation_type = "split_bonus" if block.is_split else "buy"
        unit_price = 0.0 if block.is_split else (block.unit_price_usd or 0.0)
        gross = 0.0 if block.is_split else (block.gross_value_usd or 0.0)
        trade_currency = "BRL" if block.is_split else "USD"

        notes = (
            f"split: {full_name} (delta={block.quantity})"
            if block.is_split
            else f"{full_name}"
        )

        record: dict[str, Any] = {
            "source": self.source_type,
            "broker": "Avenue",
            "trade_currency": trade_currency,
            "operation_type": operation_type,
            "operation_date": block.trade_date,
            "settlement_date": block.settle_date or block.trade_date,
            "asset_code": symbol,
            "asset_type": "stock_us",
            "quantity": block.quantity,
            "unit_price": unit_price,
            "gross_value": gross,
            "fees": 0,
            "external_id": None,
            "notes": notes,
            "source_file": file_name,
        }
        return record

    def _resolve_symbol(
        self,
        normalized_name: str,
        summary_map: dict[str, _SummaryEntry],
        _cusip: str | None,
    ) -> str | None:
        if not normalized_name:
            return None

        # First: this month's summary.
        entry = summary_map.get(normalized_name)
        if entry is not None:
            return entry.symbol

        # Fallback 1: exact-match prefix among summary entries.
        for key, value in summary_map.items():
            if normalized_name.startswith(key) or key.startswith(normalized_name):
                return value.symbol

        # Fallback 2: persistent alias cache.
        if self._alias_repo is not None and self._portfolio_id:
            cached = self._alias_repo.get(self._portfolio_id, normalized_name)
            if cached is not None:
                return cached[0]
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------


class _UnresolvedNameError(Exception):
    """Raised when a BUY block's description cannot be resolved to a ticker."""


_WS_RE = re.compile(r"\s+")


def _collapse_ws(value: str) -> str:
    return _WS_RE.sub(" ", value).strip()


def _normalize_name(value: str) -> str:
    return _collapse_ws(value).upper()


def _parse_us_date(value: str) -> str:
    """Convert MM/DD/YY → YYYY-MM-DD (assumes 20YY for two-digit year)."""
    return datetime.strptime(value, "%m/%d/%y").strftime("%Y-%m-%d")


def _parse_us_number(value: str) -> float:
    """Parse a US-formatted number ``1,234.56`` (with optional ``$`` prefix)."""
    raw = value.strip().lstrip("$").replace(",", "")
    return float(raw)


def _start_buy_block(line: str) -> _BuyBlock | None:
    """Parse the leading BOUGHT line into a partially-populated block."""
    match = _BOUGHT_RE.match(line)
    if not match:
        return None
    trade_date = _parse_us_date(match.group("trade_date"))
    settle_date = (
        _parse_us_date(match.group("settle_date"))
        if match.group("settle_date")
        else None
    )
    rest = match.group("rest").strip()

    # Split into "<description...> <qty> [$price $gross]".
    # Strategy: find the last numeric token that is preceded by description
    # text and (optionally) followed by ``$``-prefixed amounts.
    qty: float
    unit_price: float | None = None
    gross: float | None = None
    description_part: str

    if "$" in rest:
        # New-layout BOUGHT line: "DESCRIPTION QTY $PRICE $GROSS" — but the
        # 2021 layout has no ``$`` on price (only on gross). Handle both.
        before_dollar, _, after_dollar = rest.partition("$")
        before_tokens = before_dollar.strip().rsplit(maxsplit=1)
        if len(before_tokens) != 2:
            return None
        description_part, qty_str = before_tokens
        try:
            qty = _parse_us_number(qty_str)
        except ValueError:
            return None
        # after_dollar contains "PRICE [$GROSS]" — split into 1 or 2 numbers.
        after_tokens = [
            t for t in re.split(r"\s+\$?", after_dollar.strip()) if t
        ]
        try:
            if len(after_tokens) >= 2:
                unit_price = _parse_us_number(after_tokens[0])
                gross = _parse_us_number(after_tokens[-1])
            elif len(after_tokens) == 1:
                gross = _parse_us_number(after_tokens[0])
        except ValueError:
            return None
    else:
        # Pre-2022 layout WITHOUT any ``$``: "DESCRIPTION QTY PRICE GROSS"
        # OR split-bonus line: "DESCRIPTION QTY".
        tokens = rest.rsplit(maxsplit=3)
        if len(tokens) == 4:
            description_part = tokens[0]
            try:
                qty = _parse_us_number(tokens[1])
                unit_price = _parse_us_number(tokens[2])
                gross = _parse_us_number(tokens[3])
            except ValueError:
                # Likely a split — only the quantity is present at the end.
                description_part, qty_str = rest.rsplit(maxsplit=1)
                try:
                    qty = _parse_us_number(qty_str)
                except ValueError:
                    return None
                unit_price = None
                gross = None
        else:
            description_part, _, qty_str = rest.rpartition(" ")
            if not description_part:
                return None
            try:
                qty = _parse_us_number(qty_str)
            except ValueError:
                return None

    block = _BuyBlock(
        trade_date=trade_date,
        settle_date=settle_date,
        description_lines=[description_part.strip()],
        quantity=qty,
        unit_price_usd=unit_price,
        gross_value_usd=gross,
        cusip=None,
        is_split=False,
    )
    return block
