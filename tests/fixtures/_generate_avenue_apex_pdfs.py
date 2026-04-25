"""Generate synthetic Avenue/Apex monthly statement PDFs for tests.

These PDFs reproduce the textual layout that
:class:`extractors.avenue_apex_pdf.AvenueApexPdfExtractor` parses, but contain
no real account holder data. Asset descriptions and tickers (AMZN, GOOGL, KO,
JNJ, TSLA) are public information.

Run from the project root:

    uv run python tests/fixtures/_generate_avenue_apex_pdfs.py

Outputs are written next to this file. The script is committed so the fixtures
can be regenerated if the parser's expectations change.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

FAKE_ACCOUNT_NUMBER = "0AV-FAKE99-00"
FAKE_NAME = "F. AKE"
FAKE_ADDRESS_LINES = [
    "100",
    "123 FAKE STREET",
    "TEST DISTRICT",
    "00000000 TEST CITY",
    "TEST COUNTRY",
]

FONT = "Courier"
FONT_SIZE = 9
LINE_HEIGHT = 11
LEFT_MARGIN = 50
TOP_MARGIN = 750
PAGE_HEIGHT = LETTER[1]
BOTTOM_MARGIN = 60


class _PdfWriter:
    def __init__(self, path: Path) -> None:
        self._canvas = canvas.Canvas(str(path), pagesize=LETTER)
        self._canvas.setFont(FONT, FONT_SIZE)
        self._y = TOP_MARGIN

    def line(self, text: str = "") -> None:
        if self._y < BOTTOM_MARGIN:
            self.page_break()
        self._canvas.drawString(LEFT_MARGIN, self._y, text)
        self._y -= LINE_HEIGHT

    def page_break(self) -> None:
        self._canvas.showPage()
        self._canvas.setFont(FONT, FONT_SIZE)
        self._y = TOP_MARGIN

    def save(self) -> None:
        self._canvas.save()


def _statement_header(w: _PdfWriter, period: str, page_label: str) -> None:
    w.line(period)
    w.line(f"ACCOUNT NUMBER {FAKE_ACCOUNT_NUMBER} RR AVA")
    w.line(FAKE_NAME)
    w.line("Apex Clearing Corporation")
    w.line("350 N. St. Paul Street 1300")
    w.line("Dallas, TX 75201")
    w.line(page_label)
    w.line(FAKE_NAME)
    for line in FAKE_ADDRESS_LINES:
        w.line(line)
    w.line()


def _portfolio_summary_block(w: _PdfWriter, entries: list[tuple[str, str, list[str], str]]) -> None:
    """entries = [(name, symbol, continuation_lines, qty), ...]"""
    w.line("SYMBOL/                ACCOUNT       MARKET   LAST PERIOD'S  EST. ANNUAL  % OF TOTAL")
    w.line("DESCRIPTION CUSIP       TYPE QUANTITY PRICE   VALUE   MARKET VALUE  % CHANGE INCOME PORTFOLIO")
    w.line("EQUITIES / OPTIONS")
    for name, symbol, continuations, qty in entries:
        w.line(f"{name} {symbol} C {qty} $100.00 $123.45 $120.00 3% 1 5.000%")
        for cont in continuations:
            w.line(cont)
    w.line("Total Equities $1,000.00 $5 100.000%")
    w.line("Total Cash (Net Portfolio Balance) $0.01 0.000%")
    w.line("TOTAL PRICED PORTFOLIO $1,000.01 $5")
    w.line()


def _generate_april_2021(out: Path) -> None:
    """Old-layout: TRADE SETTLEMENT ACCOUNT, no PORTFOLIO SUMMARY."""
    w = _PdfWriter(out)
    _statement_header(w, "April 1, 2021 - April 30, 2021", "PAGE 1 OF 2")
    w.line("OPENING BALANCE                CLOSING BALANCE")
    w.line("Cash account $0.00             $0.00")
    w.line()
    w.page_break()

    _statement_header(w, "April 1, 2021 - April 30, 2021", "PAGE 2 OF 2")
    w.line("ACCOUNT")
    w.line("TRANSACTION DATE        DATE        TYPE   DESCRIPTION         QUANTITY   PRICE   DEBIT  CREDIT")
    w.line("FUNDS PAID AND RECEIVED")
    w.line("JOURNAL 04/30/21 C Journal from $200.00")
    w.line("Apex Clearing")
    w.line("******FAKE")
    w.line("SEN(20210430000001)")
    w.line("Total Funds Paid And Received $200.00")
    w.line("TRADE SETTLEMENT ACCOUNT")
    w.line("TRANSACTION DATE        DATE        TYPE   DESCRIPTION         QUANTITY   PRICE   DEBIT  CREDIT")
    w.line("BOUGHT 04/30/21 05/04/21 C AMAZON.COM INC 0.01426 $3,510.9997 $50.07")
    w.line("CUSIP: 023135106")
    w.line("BOUGHT 04/30/21 05/04/21 C ALPHABET INC 0.02124 2,355.11 50.02")
    w.line("CLASS A COMMON STOCK")
    w.line("CUSIP: 02079K305")
    w.line("BOUGHT 04/30/21 05/04/21 C COCA COLA COMPANY 0.37073 53.9476 20.00")
    w.line("(THE)")
    w.line("CUSIP: 191216100")
    w.line("BOUGHT 04/30/21 05/04/21 C JOHNSON & JOHNSON 0.12226 163.66 20.01")
    w.line("CUSIP: 478160104")
    w.line("BOUGHT 04/30/21 05/04/21 C TESLA INC 0.02876 694.5399 19.97")
    w.line("COMMON STOCK")
    w.line("CUSIP: 88160R101")
    w.line("Total Executed Trades Pending Settlement $160.07")
    w.save()


_SUMMARY_ENTRIES = [
    ("AMAZON.COM INC", "AMZN", [], "0.10586"),
    ("ALPHABET INC", "GOOGL", ["CLASS A COMMON STOCK"], "0.42480"),
    ("COCA COLA COMPANY", "KO", ["(THE)"], "1.09865"),
    ("JOHNSON & JOHNSON", "JNJ", [], "0.70531"),
    ("TESLA INC", "TSLA", ["COMMON STOCK"], "0.04957"),
]


def _generate_july_2022(out: Path) -> None:
    """New layout: PORTFOLIO SUMMARY + a single STK SPLIT BOUGHT for GOOGL."""
    w = _PdfWriter(out)
    _statement_header(w, "July 1, 2022 - July 31, 2022", "PAGE 1 OF 3")
    w.line("OPENING BALANCE                CLOSING BALANCE")
    w.line("Cash account $0.00             $0.01")
    w.line()
    w.page_break()

    _statement_header(w, "July 1, 2022 - July 31, 2022", "PAGE 2 OF 3")
    _portfolio_summary_block(w, _SUMMARY_ENTRIES)
    w.page_break()

    _statement_header(w, "July 1, 2022 - July 31, 2022", "PAGE 3 OF 3")
    w.line("ACCOUNT")
    w.line("TRANSACTION DATE        TYPE   DESCRIPTION                  QUANTITY   PRICE   DEBIT  CREDIT")
    w.line("BUY / SELL TRANSACTIONS")
    w.line("BOUGHT 07/20/22 C ALPHABET INC 0.40356")
    w.line("CLASS A COMMON STOCK")
    w.line("STK SPLIT ON 0.02124 SHS")
    w.line("REC 07/01/22 PAY 07/15/22")
    w.line("CUSIP: 02079K305")
    w.line("Total Buy / Sell Transactions $0.00")
    w.save()


def _generate_november_2023(out: Path) -> None:
    """New layout: PORTFOLIO SUMMARY + three BUY/SELL TRANSACTIONS."""
    w = _PdfWriter(out)
    _statement_header(w, "November 1, 2023 - November 30, 2023", "PAGE 1 OF 3")
    w.line("OPENING BALANCE                CLOSING BALANCE")
    w.line("Cash account $0.00             $0.01")
    w.line()
    w.page_break()

    _statement_header(w, "November 1, 2023 - November 30, 2023", "PAGE 2 OF 3")
    _portfolio_summary_block(w, _SUMMARY_ENTRIES)
    w.page_break()

    _statement_header(w, "November 1, 2023 - November 30, 2023", "PAGE 3 OF 3")
    w.line("ACCOUNT")
    w.line("TRANSACTION DATE        TYPE   DESCRIPTION                  QUANTITY   PRICE   DEBIT  CREDIT")
    w.line("BUY / SELL TRANSACTIONS")
    w.line("BOUGHT 11/15/23 C ALPHABET INC 2.00078 $132.448 $265.00")
    w.line("CLASS A COMMON STOCK")
    w.line("CUSIP: 02079K305")
    w.line("BOUGHT 11/15/23 C COCA COLA COMPANY 4.08599 $58.4992 $239.00")
    w.line("(THE)")
    w.line("CUSIP: 191216100")
    w.line("BOUGHT 11/15/23 C TESLA INC 1.00174 $241.4500 $241.87")
    w.line("COMMON STOCK")
    w.line("CUSIP: 88160R101")
    w.line("Total Buy / Sell Transactions $745.87")
    w.save()


def _generate_march_2026(out: Path) -> None:
    """Dividends + journals only, no BOUGHT records expected."""
    w = _PdfWriter(out)
    _statement_header(w, "March 1, 2026 - March 31, 2026", "PAGE 1 OF 2")
    w.line("OPENING BALANCE                CLOSING BALANCE")
    w.line("Cash account $0.00             $0.51")
    w.line()
    w.page_break()

    _statement_header(w, "March 1, 2026 - March 31, 2026", "PAGE 2 OF 2")
    w.line("ACCOUNT")
    w.line("TRANSACTION DATE        TYPE   DESCRIPTION                  QUANTITY   PRICE   DEBIT  CREDIT")
    w.line("DIVIDENDS AND INTEREST")
    w.line("DIVIDEND 03/03/26 C COCA COLA COMPANY $0.46 $0.51")
    w.line("(THE) WH 0.15")
    w.line("CASH DIV ON")
    w.line("1.09865 SHS")
    w.line("REC 02/15/26 PAY 03/03/26")
    w.line("NON-RES TAX WITHHELD")
    w.line("CUSIP: 191216100")
    w.line("Total Dividends And Interest $0.15 $0.51")
    w.line("FUNDS PAID AND RECEIVED")
    w.line("JOURNAL 03/04/26 C Journal from $50.00")
    w.line("Apex Clearing")
    w.line("******FAKE")
    w.line("SEN(20260304000001)")
    w.line("Total Funds Paid And Received $50.00")
    w.save()


def main() -> None:
    out_dir = Path(__file__).parent
    _generate_april_2021(out_dir / "relatorio-apex-abril-2021.pdf")
    _generate_july_2022(out_dir / "relatorio-apex-julho-2022.pdf")
    _generate_november_2023(out_dir / "relatorio-apex-novembro-2023.pdf")
    _generate_march_2026(out_dir / "relatorio-apex-marco-2026.pdf")
    print(f"Generated synthetic Avenue/Apex PDFs in {out_dir}")


if __name__ == "__main__":
    main()
