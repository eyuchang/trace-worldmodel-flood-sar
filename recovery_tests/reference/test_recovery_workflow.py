from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RECOVERY_WORKFLOW = ROOT / ".github/workflows/reference-base-validation-v2-recovery.yml"
GOVERNANCE_WORKFLOW = ROOT / ".github/workflows/reference-validation-recovery-governance.yml"
SCRIPT = ROOT / "scripts/reference/run_base_validation_recovery_v1.py"
UPLOAD_ACTION = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_ACTION = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"


def _workflow() -> dict[str, object]:
    value = yaml.safe_load(RECOVERY_WORKFLOW.read_text("utf-8"))
    assert isinstance(value, dict)
    return value


def test_recovery_workflow_is_distinct_tag_only_and_once_only() -> None:
    text = RECOVERY_WORKFLOW.read_text("utf-8")
    workflow = _workflow()

    assert "workflow_dispatch" not in text
    assert "wf-dfld-01-reference-validation-v2-recovery-v1" in text
    assert "wf-dfld-01-reference-validation-v2-recovery-original" not in text
    assert 'test "${GITHUB_RUN_ATTEMPT}" = "1"' in text
    assert "verified-no-prior-recovery-attempt" in text
    assert "cancel-in-progress: false" in text
    prior_guard = text.split("- name: Refuse any prior recovery attempt", maxsplit=1)[1].split(
        "- name: Build the source-bound recovery image", maxsplit=1
    )[0]
    assert "gh api --paginate" in prior_guard
    assert "set -euo pipefail" in prior_guard
    assert "|| true" not in prior_guard
    assert '> "${prior_ids}"' in prior_guard
    assert "|| true" not in text
    assert workflow["jobs"]

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    authorize = jobs["authorize"]
    assert isinstance(authorize, dict)
    steps = authorize["steps"]
    assert isinstance(steps, list)
    assert all(
        not isinstance(step, dict) or step.get("continue-on-error") is not True for step in steps
    )


def test_recovery_workflow_verifies_exact_failed_pre_evaluation_lifecycle() -> None:
    text = RECOVERY_WORKFLOW.read_text("utf-8")

    assert "31833291955" in text
    assert "334574314" in text
    assert "94873822352" in text
    assert "c32e0db30510f9165cdb891861cf9680b4a33c4e" in text
    assert "2cb58539425af467ac068ba7ef7500891e2fbe78" in text
    assert ".total_count == 0 and (.artifacts | length) == 0" in text
    assert '.created_at == "2026-08-14T19:26:58Z"' in text
    assert '.updated_at == "2026-08-14T19:27:52Z"' in text
    assert "Derive the protected validation-v2 list once" in text
    assert "Upload the protected plan for this workflow only" in text
    assert '.name == "shards" and .conclusion == "skipped"' in text
    assert '.name == "aggregate" and .conclusion == "skipped"' in text
    assert (
        "protected seed plan prepared: "
        "digest=2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"
    ) in text
    assert 'gh run view 31833291955 --repo "${GITHUB_REPOSITORY}" --log' in text


def test_no_raw_seed_plan_crosses_jobs_before_completed_aggregation() -> None:
    text = RECOVERY_WORKFLOW.read_text("utf-8")
    authorize, after_authorize = text.split("\n  shards:\n", maxsplit=1)
    shards, aggregate = after_authorize.split("\n  aggregate:\n", maxsplit=1)

    assert "seed_plan" not in authorize
    assert "download-artifact" not in shards
    assert "--seed-plan" not in shards
    assert "run_base_validation_recovery_v1.py" in shards
    assert " shard " in shards
    assert "reference_validation_v2_seed_plan.json" in aggregate
    assert "steps.completeness.outputs.complete == 'true'" in aggregate
    assert "steps.aggregate_execution.outcome == 'success'" in aggregate
    assert "steps.artifact_preflight.outcome == 'success'" in aggregate


def test_output_containers_and_artifacts_enforce_runner_ownership() -> None:
    text = RECOVERY_WORKFLOW.read_text("utf-8")

    assert text.count('--user "$(id -u):$(id -g)"') >= 5
    assert "umask 077" in text
    assert text.count("stat -c '%u'") >= 2
    assert text.count("test ! -L") >= 2
    assert text.count("test -r") >= 2
    assert "chmod 644" not in text
    assert text.count("--network none") == 6
    assert UPLOAD_ACTION in text
    assert DOWNLOAD_ACTION in text
    assert (
        "docker.io/library/python@"
        "sha256:88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d"
    ) in text
    assert (
        "docker.io/library/python@"
        "sha256:3b3706a90cb23f04fabb0d255824f9a70ceb46177041898133dd5a35f3a50f0a"
    ) in text


def test_interrupted_recovery_uploads_seed_free_continuation_evidence() -> None:
    text = RECOVERY_WORKFLOW.read_text("utf-8")

    assert "reference_validation_recovery_continuation_plan_v1.json" in text
    assert "completed_shards_must_not_rerun" not in text
    interrupted = text.split("Upload interrupted recovery evidence without raw seeds", maxsplit=1)[
        1
    ]
    assert "reference_validation_v2_seed_plan.json" not in interrupted
    assert "recovery-shards/*.json" in interrupted
    assert "reference_validation_recovery_interruption_record_v1.json" in text
    assert "reference_validation_recovery_upload_failure_v1.json" in text
    assert "steps.completed_upload.outcome == 'failure'" in text
    assert "normalization_valid=false" in text
    assert "stage=normalization" in text
    assert "stage=aggregation" in text
    assert "stage=artifact-preflight" in text


def test_branch_governance_workflow_and_script_cannot_prepare_a_plan() -> None:
    governance = GOVERNANCE_WORKFLOW.read_text("utf-8")
    script = SCRIPT.read_text("utf-8")

    assert "recovery_tests/reference" in governance
    assert "verify-manifest" in governance
    assert "fetch-depth: 2" in governance
    assert "git diff --check HEAD^ HEAD" in governance
    assert "authorize" not in governance
    assert 'commands.add_parser("prepare")' not in script
    assert "prepare_protected_seed_plan" not in script
    assert 'commands.add_parser("authorize")' in script
