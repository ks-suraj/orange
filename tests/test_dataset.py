"""The evaluation dataset is frozen: regenerating it must reproduce the committed files exactly, the
answers must not change, and generated evidence must be internally consistent."""

import hashlib
import importlib.util
import json
import random
import sys

import pytest

from incident_investigator.config import DATA_DIR, PROJECT_ROOT
from incident_investigator.evaluation.metrics import load_ground_truth
from incident_investigator.scenarios import load_scenario

FROZEN_ANSWERS = {  # incident: (expected_inconclusive, root-cause services, categories)
    "S01": (False, ["checkout-service"], ["deployment_regression"]),
    "S02": (False, ["payment-service"], ["config_error"]),
    "S03": (False, ["notification-worker"], ["resource_exhaustion", "deployment_regression"]),
    "S04": (False, ["payment-provider"], ["dependency_failure"]),
    "S05": (False, ["auth-service"], ["certificate_expiry"]),
    "S06": (False, ["inventory-db"], ["infrastructure_failure"]),
    "S07": (False, ["checkout-service", "api-gateway"], ["traffic_surge"]),
    "S08": (False, ["payment-service"], ["deployment_regression"]),
    "S09": (False, ["inventory-service"], ["config_error"]),
    "S10": (True, [], []),
    "S11": (False, ["payments-db"], ["resource_exhaustion"]),
    "S12": (True, [], []),
}


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("generate_scenarios", PROJECT_ROOT / "scripts" / "generate_scenarios.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def test_ground_truth_answers_are_frozen():
    for sid, (inconclusive, services, categories) in FROZEN_ANSWERS.items():
        gt = load_ground_truth(sid)
        assert (gt.expected_inconclusive, gt.root_cause_services, [c.value for c in gt.root_cause_categories]) == \
            (inconclusive, services, categories), sid


def test_committed_dataset_matches_manifest():
    manifest = json.loads((DATA_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 12 * 7
    for rel, digest in manifest["files"].items():
        assert hashlib.sha256((DATA_DIR / rel).read_bytes()).hexdigest() == digest, rel


def test_regeneration_is_deterministic_and_reproduces_committed_data(generator, tmp_path):
    generator.main(tmp_path)
    fresh = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    committed = json.loads((DATA_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert fresh == committed


def _lines(sid, service, after_onset, level=None):
    sc = load_scenario(sid)
    onset_hour = int(sc.brief.window_start[11:13]) + 1  # window starts 60 min before onset, on the hour
    return [l for l in sc.data["logs"] if l["service"] == service and (int(l["ts"][11:13]) >= onset_hour) == after_onset
            and (level is None or l["level"] == level)]


def test_background_logs_follow_a_traffic_collapse():
    # S05: auth-service request rate falls ~96% at onset; its logs must fall with it.
    before, after = len(_lines("S05", "auth-service", False)), len(_lines("S05", "auth-service", True))
    assert before >= 15 and after <= 2


def test_background_logs_follow_a_traffic_surge():
    # S07: gateway traffic x4 at onset -> clearly more log lines per minute (60 min before vs 30 min after).
    before, after = len(_lines("S07", "api-gateway", False)) / 60, len(_lines("S07", "api-gateway", True)) / 30
    assert after > 2.5 * before


def test_success_logs_thin_out_as_error_rate_rises(generator):
    # S04: payment-service at 41% errors after onset should keep ~59% of routine INFO lines. One committed
    # sample is small and noisy, so check the mechanism over many seeds.
    spec = next(s for s in generator.SPECS if s.id == "S04")
    assert generator.metric_value(spec, "payment-service", "error_rate", 10) == 41
    before = after = 0
    for seed in range(100):
        for r in generator.build_logs(spec, random.Random(seed))[0]:
            if r["service"] == "payment-service" and r["level"] == "INFO":
                if r["ts"] < "2026-09-04T16:00:00Z":
                    before += 1
                else:
                    after += 1
    ratio = (after / 31) / (before / 60)
    assert 0.45 < ratio < 0.7


def test_s05_tls_evidence_is_consistent_and_decoy_preserved():
    logs = load_scenario("S05").data["logs"]
    checkout = [l["message"] for l in logs if l["service"] == "checkout-service" and l["level"] == "ERROR"]
    gateway = [l["message"] for l in logs if l["service"] == "api-gateway" and l["level"] == "ERROR"]
    assert any("PKIX path validation failed" in m and "auth.internal:8443" in m for m in checkout)
    assert not any("remote error: tls: handshake failure" in m for l in logs for m in [l["message"]])
    assert any("certificate has expired" in m for m in gateway)
    # checkout's client-side validation error points at its peer, so the checkout deploy stays a decoy
    gt = load_ground_truth("S05")
    assert {"service": "checkout-service", "category": "deployment_regression"} in gt.decoy_hypotheses
    changes = {c["id"]: c for c in load_scenario("S05").data["changes"]}
    assert any(changes[g[0]]["service"] == "checkout-service" for g in gt.misleading_evidence if g[0].startswith("C"))
