"""IRPF report builder — orchestrates classifier + repositories.

V1 scope: a single `renda-variavel` portfolio, ações BR + FII (FIAGRO is
treated as `fii` until reclassified manually). All monetary values flow as
integer cents. The builder is pure relative to its dependencies — they are
injected.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from domain.irpf.classifier import (
    SECTION_CATEGORIES,
    SECTION_TITLES,
    bem_direito_section,
    classify,
)
from domain.irpf.discriminacao import format_discriminacao
from domain.irpf.models import (
    IrpfBemDireitoExtra,
    IrpfReport,
    IrpfRow,
    IrpfSection,
)
from domain.position_service import PositionService
from storage.repository.asset_metadata import (
    AssetMetadataRepository,
    infer_asset_class_irpf,
)
from storage.repository.operations import OperationRepository

_PROVENT_TYPES: tuple[str, ...] = ("dividend", "jcp", "rendimento", "split_bonus")
_PROVISIONED_OP_TYPES: tuple[str, ...] = ("dividend", "jcp", "rendimento")


class IrpfReportBuilder:
    def __init__(
        self,
        operations_repo: OperationRepository,
        asset_metadata_repo: AssetMetadataRepository,
        position_service: PositionService | None = None,
    ) -> None:
        self._ops = operations_repo
        self._meta = asset_metadata_repo
        self._positions = position_service or PositionService()

    def build(self, portfolio_id: str, base_year: int) -> IrpfReport:
        year_start = f"{base_year}-01-01"
        year_end = f"{base_year}-12-31"
        prev_year_end = f"{base_year - 1}-12-31"

        # --------------------------------------------------------------
        # Carregar todas as operações do portfólio uma única vez.
        # --------------------------------------------------------------
        all_ops = self._ops.list_all_by_portfolio(portfolio_id)
        ops_in_year = [
            op for op in all_ops if year_start <= op["operation_date"] <= year_end
        ]

        asset_codes = {op["asset_code"] for op in all_ops}
        meta_map = self._meta.get_many(asset_codes)
        report_warnings: list[str] = []

        def get_class(asset_code: str, asset_type: str | None) -> str:
            metadata = meta_map.get(asset_code.upper())
            if metadata is not None:
                return metadata.asset_class_irpf
            return infer_asset_class_irpf(asset_code, asset_type)

        def get_cnpj(asset_code: str) -> str | None:
            metadata = meta_map.get(asset_code.upper())
            return metadata.cnpj if metadata is not None else None

        def get_official_name(asset_code: str, fallback: str | None) -> str | None:
            metadata = meta_map.get(asset_code.upper())
            if metadata is not None and metadata.asset_name_oficial:
                return metadata.asset_name_oficial
            return fallback

        # --------------------------------------------------------------
        # Provenientes (Rendimentos Isentos + Tributação Exclusiva).
        # Provenientes provisionados (settlement_date no ano seguinte)
        # NÃO entram aqui — vão apenas para Bens e Direitos 99-07/99-99.
        # --------------------------------------------------------------
        # Estrutura: section_code -> asset_code -> aggregated row state.
        provent_rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

        for op in ops_in_year:
            op_type = op["operation_type"]
            if op_type not in _PROVENT_TYPES:
                continue

            settlement = op.get("settlement_date")
            if (
                op_type in _PROVISIONED_OP_TYPES
                and settlement is not None
                and settlement > year_end
            ):
                # Pago apenas no ano seguinte → conta só em Bens e Direitos.
                continue

            asset_code = op["asset_code"]
            cls = get_class(asset_code, op.get("asset_type"))
            section_code = classify(cls, op_type)
            if section_code is None:
                continue

            # Cód. 10 (JCP) usa LÍQUIDO = gross - fees.
            # Cód. 09/99/18 usam BRUTO (gross_value).
            if section_code == "10":
                value = int(op["gross_value"]) - int(op["fees"])
            else:
                value = int(op["gross_value"])

            asset_state = provent_rows[section_code].setdefault(
                asset_code,
                {
                    "asset_code": asset_code,
                    "asset_name": op.get("asset_name"),
                    "value_cents": 0,
                },
            )
            asset_state["value_cents"] += value
            if not asset_state["asset_name"] and op.get("asset_name"):
                asset_state["asset_name"] = op["asset_name"]

        provent_sections: list[IrpfSection] = []
        for section_code in ("09", "18", "99", "10"):
            row_map = provent_rows.get(section_code, {})
            rows: list[IrpfRow] = []
            for asset_code in sorted(row_map.keys()):
                state = row_map[asset_code]
                cnpj = get_cnpj(asset_code)
                warnings: list[str] = []
                if cnpj is None:
                    warnings.append("cnpj_missing")
                if state["value_cents"] == 0:
                    warnings.append("valor_zero")
                rows.append(
                    IrpfRow(
                        asset_code=asset_code,
                        asset_name=get_official_name(asset_code, state["asset_name"]),
                        cnpj=cnpj,
                        value_cents=int(state["value_cents"]),
                        warnings=warnings,
                    )
                )
            if rows:
                provent_sections.append(
                    IrpfSection(
                        code=section_code,
                        title=SECTION_TITLES[section_code],
                        category=SECTION_CATEGORIES[section_code],  # type: ignore[arg-type]
                        rows=rows,
                    )
                )

        # --------------------------------------------------------------
        # Bens e Direitos: snapshots em 31/12 do ano-base e do ano anterior.
        # --------------------------------------------------------------
        positions_now = self._positions.calculate_as_of(all_ops, portfolio_id, year_end)
        positions_prev = {
            p.asset_code: p
            for p in self._positions.calculate_as_of(all_ops, portfolio_id, prev_year_end)
        }

        bem_rows: dict[str, list[IrpfRow]] = defaultdict(list)
        for pos in positions_now:
            cls = get_class(pos.asset_code, pos.asset_type)
            section_code = bem_direito_section(cls)
            if section_code is None:
                # Fora do escopo V1 (BDR/ETF/etc.) — ignorar silenciosamente.
                continue

            quantity = float(pos.quantity)
            total_cents = int(pos.total_cost)
            if quantity <= 0 and total_cents <= 0:
                # Sem posição em 31/12 — só relevante se houve posição anterior.
                prev = positions_prev.get(pos.asset_code)
                if prev is None or float(prev.quantity) <= 0:
                    continue

            avg_price_cents = int(pos.avg_price)
            cnpj = get_cnpj(pos.asset_code)
            asset_name = get_official_name(pos.asset_code, pos.asset_name)

            prev = positions_prev.get(pos.asset_code)
            prev_total = int(prev.total_cost) if prev else 0
            prev_qty = float(prev.quantity) if prev else 0.0

            extra = IrpfBemDireitoExtra(
                quantity=quantity,
                avg_price_cents=avg_price_cents,
                total_cents=total_cents,
                previous_total_cents=prev_total,
                previous_quantity=prev_qty,
            )

            row_warnings: list[str] = []
            if cnpj is None:
                row_warnings.append("cnpj_missing")
            if total_cents == 0 and quantity == 0 and prev_total > 0:
                row_warnings.append("posicao_zerada_no_ano")

            discriminacao = format_discriminacao(
                cls,
                asset_code=pos.asset_code,
                asset_name=asset_name,
                quantity=quantity,
                avg_price_cents=avg_price_cents,
                total_cents=total_cents,
            )

            bem_rows[section_code].append(
                IrpfRow(
                    asset_code=pos.asset_code,
                    asset_name=asset_name,
                    cnpj=cnpj,
                    value_cents=total_cents,
                    extra=extra,
                    discriminacao=discriminacao,
                    warnings=row_warnings,
                )
            )

        bem_sections: list[IrpfSection] = []
        for section_code in ("03-01", "07-03", "07-02"):
            rows = sorted(
                bem_rows.get(section_code, []),
                key=lambda r: r.asset_code,
            )
            if rows:
                bem_sections.append(
                    IrpfSection(
                        code=section_code,
                        title=SECTION_TITLES[section_code],
                        category="bem_direito",
                        rows=rows,
                    )
                )

        # --------------------------------------------------------------
        # 99-07 / 99-99 — provisões a receber em 31/12 do ano-base.
        # Heurística: operation_date <= 31/12/AAAA e settlement_date > 31/12/AAAA.
        # settlement_date NULL é tratado como pago (não provisionado).
        # --------------------------------------------------------------
        provisioned_rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for op in all_ops:
            op_type = op["operation_type"]
            if op_type not in _PROVISIONED_OP_TYPES:
                continue
            if op["operation_date"] > year_end:
                continue
            settlement = op.get("settlement_date")
            if settlement is None or settlement <= year_end:
                continue

            asset_code = op["asset_code"]
            cls = get_class(asset_code, op.get("asset_type"))
            if op_type == "jcp" and cls == "acao":
                section_code = "99-07"
                value = int(op["gross_value"]) - int(op["fees"])
            elif op_type in {"dividend", "rendimento"}:
                section_code = "99-99"
                value = int(op["gross_value"])
            else:
                continue

            asset_state = provisioned_rows[section_code].setdefault(
                asset_code,
                {
                    "asset_code": asset_code,
                    "asset_name": op.get("asset_name"),
                    "value_cents": 0,
                },
            )
            asset_state["value_cents"] += value
            if not asset_state["asset_name"] and op.get("asset_name"):
                asset_state["asset_name"] = op["asset_name"]

        provisioned_sections: list[IrpfSection] = []
        for section_code in ("99-07", "99-99"):
            row_map = provisioned_rows.get(section_code, {})
            rows = []
            for asset_code in sorted(row_map.keys()):
                state = row_map[asset_code]
                cnpj = get_cnpj(asset_code)
                warnings = []
                if cnpj is None:
                    warnings.append("cnpj_missing")
                rows.append(
                    IrpfRow(
                        asset_code=asset_code,
                        asset_name=get_official_name(asset_code, state["asset_name"]),
                        cnpj=cnpj,
                        value_cents=int(state["value_cents"]),
                        warnings=warnings,
                    )
                )
            if rows:
                provisioned_sections.append(
                    IrpfSection(
                        code=section_code,
                        title=SECTION_TITLES[section_code],
                        category="bem_direito",
                        rows=rows,
                    )
                )

        # --------------------------------------------------------------
        # Avisos globais.
        # --------------------------------------------------------------
        missing_meta = sorted(c for c in asset_codes if c.upper() not in meta_map)
        if missing_meta:
            report_warnings.append(
                "asset_metadata_missing:" + ",".join(missing_meta)
            )

        all_sections = provent_sections + bem_sections + provisioned_sections

        return IrpfReport(
            portfolio_id=portfolio_id,
            base_year=base_year,
            sections=all_sections,
            generated_at=datetime.now(UTC),
            warnings=report_warnings,
        )
