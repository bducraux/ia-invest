from domain.position_service import PositionService


def _op(asset, op_type, date, qty, gross, fees=0, op_id=0):
    return {
        "id": op_id,
        "asset_code": asset,
        "asset_type": "stock",
        "asset_name": asset,
        "operation_type": op_type,
        "operation_date": date,
        "quantity": qty,
        "gross_value": gross,
        "fees": fees,
    }


def test_calculate_as_of_filters_future_operations() -> None:
    svc = PositionService()
    ops = [
        _op("X", "buy", "2023-06-15", 100, 100000, op_id=1),
        _op("X", "buy", "2024-04-10", 50, 60000, op_id=2),
        _op("X", "buy", "2025-01-15", 30, 40000, op_id=3),
    ]
    snapshot = {p.asset_code: p for p in svc.calculate_as_of(ops, "p1", "2024-12-31")}
    assert snapshot["X"].quantity == 150
    assert snapshot["X"].total_cost == 160000


def test_calculate_as_of_inclusive_endpoint() -> None:
    svc = PositionService()
    ops = [
        _op("X", "buy", "2024-12-31", 10, 10000, op_id=1),
    ]
    snapshot = svc.calculate_as_of(ops, "p1", "2024-12-31")
    assert snapshot[0].quantity == 10


def test_calculate_as_of_empty_when_all_in_future() -> None:
    svc = PositionService()
    ops = [
        _op("X", "buy", "2025-01-01", 10, 10000, op_id=1),
    ]
    assert svc.calculate_as_of(ops, "p1", "2024-12-31") == []
