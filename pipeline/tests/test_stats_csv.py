import pytest

from metashift.core.errors import MetashiftError
from metashift.core.stats_csv import read_stats_csv


def test_stats_csv_handles_bom_percent_and_blank_tier(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_bytes(
        "﻿entity,win_rate,pick_rate,ban_rate,tier\nahri, 49.1% ,6.2,3.0,\n".encode()
    )
    [row] = read_stats_csv(p)
    assert (row.entity, row.win_rate, row.tier) == ("ahri", 49.1, None)
    assert (row.pick_rate, row.ban_rate) == (6.2, 3.0)


def test_stats_csv_bad_number_names_line_and_column(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_text(
        "entity,win_rate,pick_rate,ban_rate,tier\nahri,50,1,1,S\nkaisa,abc,1,1,A\n",
        encoding="utf-8",
    )
    with pytest.raises(MetashiftError, match="line 3: bad win_rate 'abc'"):
        read_stats_csv(p)


def test_stats_csv_first_data_row_is_line_two(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_text("entity,win_rate,pick_rate,ban_rate,tier\nahri,abc,1,1,S\n", encoding="utf-8")
    with pytest.raises(MetashiftError, match="line 2: bad win_rate 'abc'"):
        read_stats_csv(p)


def test_stats_csv_empty_cells_are_none_and_headers_ignore_case(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_text(
        " Entity ,WIN_RATE,Pick_Rate,ban_rate,Tier\nAhri,,6.2 %,,S+\n\n", encoding="utf-8"
    )
    [row] = read_stats_csv(p)
    assert (row.entity, row.win_rate, row.pick_rate, row.ban_rate, row.tier) == (
        "Ahri",
        None,
        6.2,
        None,
        "S+",
    )


def test_stats_csv_out_of_range_rate_is_a_clean_error(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_text("entity,win_rate,pick_rate,ban_rate,tier\nahri,149,1,1,S\n", encoding="utf-8")
    with pytest.raises(MetashiftError, match="line 2: bad win_rate '149'"):
        read_stats_csv(p)


def test_stats_csv_missing_column_lists_expected_columns(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_text("entity,win_rate\nahri,50\n", encoding="utf-8")
    with pytest.raises(MetashiftError, match="entity,win_rate,pick_rate,ban_rate,tier"):
        read_stats_csv(p)
