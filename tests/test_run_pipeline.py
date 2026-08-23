"""
Pipeline wiring tests.

run_pipeline.py used to execute the entire pipeline at import time (no
main() guard), making it unimportable and untestable. These tests pin the
fixed behaviour: import is side-effect free; main() is the only entrypoint.
"""
import pytest

from scripts import run_pipeline as rp


def test_import_has_no_side_effects():
    # Importing must not create artifacts or raise; module exposes main().
    assert callable(rp.main)
    assert rp.PROJECT_ROOT.exists()


def test_main_aborts_on_empty_ingestion(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(
        rp, "load_telemetry_auto",
        lambda raw_path, rejected_path: (pd.DataFrame(), {"data_source": "local"}),
    )

    with pytest.raises(RuntimeError, match="no valid events"):
        rp.main()
