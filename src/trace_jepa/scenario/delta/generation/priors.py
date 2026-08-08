"""Within-predictor prior selection for the pi scenario axis."""

from trace_jepa.scenario.delta.domain import DeltaScenarioConfig, PriorProfileArtifact


def generate_prior_profile(config: DeltaScenarioConfig) -> PriorProfileArtifact:
    """Select the frozen prior profile without changing predictor identity."""

    if config.axes.pi >= 0.8:
        profile_id, accuracy = "delta-prior-high-v1", 900
    elif config.axes.pi >= 0.55:
        profile_id, accuracy = "delta-prior-medium-v1", 650
    else:
        profile_id, accuracy = "delta-prior-low-v1", 400
    return PriorProfileArtifact(
        profile_id=profile_id,
        schema_version="delta-predictor-prior-profile-v1",
        calibration_version=f"{profile_id}-calibration-v1",
        prior_accuracy_milli=accuracy,
        selected_by_pi=config.axes.pi,
    )
