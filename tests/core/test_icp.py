"""
Tests for the ICP config loader. Loads the real configs/icp_ai_native_b2b.yaml
(not a mock) — this file IS the artifact under test; a fixture copy would
let the real config drift out of sync with what's actually validated.
"""
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.icp import ICPConfig

REAL_ICP_PATH = Path(__file__).parents[2] / "configs" / "icp_ai_native_b2b.yaml"


def test_real_icp_config_loads_and_validates():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)

    assert icp.name
    assert len(icp.criteria) >= 3
    assert all(0 <= c.weight <= 100 for c in icp.criteria)


def test_icp_score_thresholds_are_ordered_sensibly():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)

    assert icp.score_thresholds.reject < icp.score_thresholds.review
    assert icp.score_thresholds.review <= 100


def test_icp_as_prompt_block_includes_all_criteria_labels():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)

    block = icp.as_prompt_block()

    assert icp.name in block
    for criterion in icp.criteria:
        assert criterion.label in block


def test_band_for_score_matches_thresholds():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)
    t = icp.score_thresholds

    assert icp.band_for_score(0) == "reject"
    assert icp.band_for_score(t.reject) == "reject"
    assert icp.band_for_score(t.reject + 1) == "review"
    assert icp.band_for_score(t.review) == "review"
    assert icp.band_for_score(t.review + 1) == "ready"
    assert icp.band_for_score(100) == "ready"


def test_missing_icp_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        ICPConfig.from_yaml("configs/does_not_exist.yaml")


def test_invalid_icp_yaml_raises_validation_error(tmp_path):
    bad_yaml = tmp_path / "bad_icp.yaml"
    bad_yaml.write_text("name: Missing required fields\n")

    with pytest.raises(ValidationError):
        ICPConfig.from_yaml(bad_yaml)
