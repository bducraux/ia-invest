from domain.irpf.classifier import bem_direito_section, classify


def test_dividend_acao_section_09() -> None:
    assert classify("acao", "dividend") == "09"


def test_dividend_fii_section_99() -> None:
    assert classify("fii", "dividend") == "99"
    assert classify("fiagro", "dividend") == "99"


def test_rendimento_only_for_fii() -> None:
    assert classify("fii", "rendimento") == "99"
    assert classify("fiagro", "rendimento") == "99"
    assert classify("acao", "rendimento") is None


def test_jcp_only_for_acao() -> None:
    assert classify("acao", "jcp") == "10"
    assert classify("fii", "jcp") is None


def test_bonificacao_only_for_acao() -> None:
    assert classify("acao", "split_bonus") == "18"
    assert classify("fii", "split_bonus") is None


def test_unknown_combinations_return_none() -> None:
    assert classify("bdr", "dividend") is None
    assert classify("etf", "dividend") is None
    assert classify("acao", "buy") is None
    assert classify(None, "dividend") is None
    assert classify("acao", "") is None


def test_bem_direito_section_codes() -> None:
    assert bem_direito_section("acao") == "03-01"
    assert bem_direito_section("fii") == "07-03"
    assert bem_direito_section("fiagro") == "07-02"
    assert bem_direito_section("bdr") is None
    assert bem_direito_section(None) is None
