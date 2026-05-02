from domain.irpf.discriminacao import format_discriminacao


def test_acoes_plural() -> None:
    text = format_discriminacao(
        "acao",
        asset_code="ITSA4",
        asset_name="ITAUSA S.A.",
        quantity=665,
        avg_price_cents=823,
        total_cents=547607,
    )
    assert text == "665 ações ITSA4 ITAUSA S.A.. Preço médio de 8,23 totalizando 5.476,07"


def test_acao_singular() -> None:
    text = format_discriminacao(
        "acao",
        asset_code="WEGE3",
        asset_name="WEG S.A.",
        quantity=1,
        avg_price_cents=3559,
        total_cents=3559,
    )
    assert text.startswith("1 ação WEGE3 WEG S.A..")


def test_fii_cotas_plural_reference() -> None:
    text = format_discriminacao(
        "fii",
        asset_code="SAPR11",
        asset_name="CIA SANEAMENTO DO PARANA - SANEPAR",
        quantity=278,
        avg_price_cents=2773,
        total_cents=770943,
    )
    assert text == (
        "278 cotas SAPR11 CIA SANEAMENTO DO PARANA - SANEPAR. "
        "Preço médio de 27,73 totalizando 7.709,43"
    )


def test_fiagro_cota_singular() -> None:
    text = format_discriminacao(
        "fiagro",
        asset_code="BTAL11",
        asset_name="FII BTG AGRO",
        quantity=1,
        avg_price_cents=9958,
        total_cents=9958,
    )
    assert text.startswith("1 cota BTAL11 FII BTG AGRO.")


def test_thousand_separator_and_decimal_comma() -> None:
    text = format_discriminacao(
        "acao",
        asset_code="X",
        asset_name=None,
        quantity=10,
        avg_price_cents=123456,
        total_cents=1234567,
    )
    # 1234.56 → 1.234,56 ; 12345.67 → 12.345,67
    assert "1.234,56" in text
    assert "12.345,67" in text


def test_zero_value_renders_zero_zero() -> None:
    text = format_discriminacao(
        "acao",
        asset_code="ITSA4",
        asset_name="ITAUSA S.A.",
        quantity=0,
        avg_price_cents=0,
        total_cents=0,
    )
    assert "0,00" in text
