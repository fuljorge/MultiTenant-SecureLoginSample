"""Células da exportação de auditoria (T068): sem fórmulas de planilha (injeção de CSV)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cap_control_plane.audit.api import csv_cell


@pytest.mark.parametrize("value", ["=HYPERLINK(1)", "+1", "-1", "@SUM(A1)", "\tx"])
def test_neutraliza_formulas(value: str) -> None:
    assert csv_cell(value) == "'" + value


def test_mantem_texto_comum_vazio_e_data_em_utc() -> None:
    assert csv_cell("auth.login") == "auth.login"
    assert csv_cell(None) == ""
    assert csv_cell(datetime(2026, 10, 3, 12, 0, tzinfo=UTC)) == "2026-10-03T12:00:00+00:00"
