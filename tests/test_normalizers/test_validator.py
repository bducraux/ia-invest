"""Tests for validator helpers."""

from __future__ import annotations

import pytest

from normalizers.validator import (
    infer_asset_type,
    normalise_asset_code,
    normalise_operation_type,
    parse_date,
    parse_monetary_cents,
    parse_quantity,
)


class TestParseDate:
    def test_iso_format(self) -> None:
        assert parse_date("2024-01-15") == "2024-01-15"

    def test_br_format(self) -> None:
        assert parse_date("15/01/2024") == "2024-01-15"

    def test_dashes_br(self) -> None:
        assert parse_date("15-01-2024") == "2024-01-15"

    def test_datetime_truncated(self) -> None:
        assert parse_date("2024-01-15 10:30:00") == "2024-01-15"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_date("")

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_date(None)

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestParseQuantity:
    def test_integer(self) -> None:
        assert parse_quantity("100") == 100.0

    def test_decimal_dot(self) -> None:
        assert parse_quantity("0.5") == 0.5

    def test_decimal_comma(self) -> None:
        assert parse_quantity("1234,56") == 1234.56

    def test_thousands_separator(self) -> None:
        assert parse_quantity("1.234,56") == 1234.56

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_quantity("-10")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_quantity("")


class TestParseMonetaryCents:
    def test_integer_value(self) -> None:
        assert parse_monetary_cents("100") == 10000

    def test_decimal_dot(self) -> None:
        assert parse_monetary_cents("35.50") == 3550

    def test_decimal_comma(self) -> None:
        assert parse_monetary_cents("35,50") == 3550

    def test_br_thousands(self) -> None:
        assert parse_monetary_cents("1.234,56") == 123456

    def test_empty_returns_zero(self) -> None:
        assert parse_monetary_cents("") == 0

    def test_none_returns_zero(self) -> None:
        assert parse_monetary_cents(None) == 0


class TestNormaliseOperationType:
    def test_buy_aliases(self) -> None:
        assert normalise_operation_type("compra") == "buy"
        assert normalise_operation_type("C") == "buy"
        assert normalise_operation_type("buy") == "buy"

    def test_sell_aliases(self) -> None:
        assert normalise_operation_type("venda") == "sell"
        assert normalise_operation_type("V") == "sell"
        assert normalise_operation_type("sell") == "sell"

    def test_dividend(self) -> None:
        assert normalise_operation_type("dividendo") == "dividend"

    def test_split(self) -> None:
        assert normalise_operation_type("desdobramento") == "split"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            normalise_operation_type("xyz_invalid")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            normalise_operation_type("")


class TestInferAssetType:
    def test_fii(self) -> None:
        assert infer_asset_type("HGLG11") == "fii"

    def test_stock_3(self) -> None:
        assert infer_asset_type("PETR4") == "stock"

    def test_bdr(self) -> None:
        assert infer_asset_type("AAPL34") == "bdr"


class TestNormaliseAssetCode:
    def test_uppercase_preserved(self) -> None:
        assert normalise_asset_code("btc") == "BTC"

    def test_rndr_alias_to_render(self) -> None:
        assert normalise_asset_code("RNDR") == "RENDER"

    def test_matic_alias_to_pol(self) -> None:
        assert normalise_asset_code("MATIC") == "POL"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            normalise_asset_code("")
