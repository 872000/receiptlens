"""End-to-end tests driving the CLI on the bundled demo data."""
import sqlite3

import pytest

from receiptlens import cli, store


@pytest.fixture()
def workdir(tmp_path, receipts_dir):
    db = tmp_path / "e2e.db"
    out = tmp_path / "reports"
    return {"db": str(db), "out": str(out), "receipts": str(receipts_dir), "tmp": tmp_path}


def test_full_demo_flow(workdir, capsys):
    assert cli.main(["--db", workdir["db"], "ingest", workdir["receipts"]]) == 0
    out = capsys.readouterr().out
    assert "Ingested 8 receipt(s)" in out
    assert "skipped 2 duplicate(s)" in out  # the two .png fall back to paired .txt

    assert cli.main(["--db", workdir["db"], "report",
                     "--month", "2026-09", "--out", workdir["out"]]) == 0
    out = capsys.readouterr().out
    assert "September 2026" in out
    assert "groceries" in out

    assert cli.main(["--db", workdir["db"], "categories", "--review"]) == 0
    out = capsys.readouterr().out
    assert "WORK GLOVES" in out

    assert cli.main(["--db", workdir["db"], "categories"]) == 0


def test_reingest_is_idempotent(workdir, capsys):
    cli.main(["--db", workdir["db"], "ingest", workdir["receipts"]])
    capsys.readouterr()
    assert cli.main(["--db", workdir["db"], "ingest", workdir["receipts"]]) == 0
    assert "Ingested 0 receipt(s)" in capsys.readouterr().out
    conn = sqlite3.connect(workdir["db"])
    assert conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 8


def test_recategorize_command(workdir, capsys):
    cli.main(["--db", workdir["db"], "ingest", workdir["receipts"]])
    capsys.readouterr()
    conn = store.connect(workdir["db"])
    row = store.review_queue(conn)[0]
    assert cli.main(["--db", workdir["db"], "recategorize",
                     str(row["id"]), "shopping"]) == 0
    assert "shopping" in capsys.readouterr().out
    assert cli.main(["--db", workdir["db"], "recategorize", "424242", "shopping"]) == 1


def test_report_month_flag_validation(workdir):
    with pytest.raises(SystemExit):
        cli.main(["--db", workdir["db"], "report", "--month", "not-a-month"])


def test_ingest_missing_path(workdir, capsys):
    assert cli.main(["--db", workdir["db"], "ingest", "/does/not/exist"]) == 1
    assert "Nothing to ingest" in capsys.readouterr().out
