# DINO-WM Development Confirmation and Held-Out Results

## Method

The DINO-WM integration uses a frozen DINOv2 ViT-S/14 encoder and a learned
action-conditioned spatial transformer to predict future patch embeddings. The
predictor consumes synchronized current observations and candidate actions; it
does not receive latent simulator truth. A calibrated Flood-SAR outcome head maps
the predicted future representation and controller-visible structured inputs to
the existing route outcomes.

The prospectively registered development confirmation used 600 independent
episodes and 1,200 transitions. Complete episodes were separated across train,
tuning, calibration, and development-validation splits. The held-out evaluation
used 400 new episodes and 800 transitions. The exact code, data, encoder,
predictor, calibration, controls, and development report were frozen before test
generation. No fitting, tuning, or calibration was performed after the test split
was opened.

## Development confirmation

The registered gate passed. Future-latent MSE was 1.7951 for DINO-WM versus
2.8678 for persistence. The paired DINO-WM-minus-persistence difference was
-1.0727 (95% interval [-1.1795, -0.9624]). The correct-action prediction also
outperformed the shuffled-action control by point estimate.

For downstream outcomes, fused predicted-future features improved over the
structured baseline on both primary point estimates: Brier score decreased from
0.2153 to 0.1450 and all-target MSE decreased from 0.06294 to 0.03875. The
all-target MSE difference was supported by its paired 95% interval; the Brier
interval crossed zero.

## Frozen held-out evaluation

The dynamics result replicated on 400 held-out episodes. Future-latent MSE was
1.7963 for DINO-WM, 2.9052 for persistence, and 1.8058 with shuffled actions.
The paired DINO-WM-minus-persistence interval was [-1.1521, -1.0683], and the
DINO-WM-minus-shuffled-action interval was [-0.01381, -0.00552].

The fused predicted-future model achieved a Brier score of 0.1536 and all-target
MSE of 0.04074, compared with 0.1794 and 0.05341 for structured-only. The paired
all-target MSE difference was -0.01267 (95% interval [-0.02083, -0.00498]). The
paired Brier difference was -0.02577 (95% interval [-0.05466, 0.00428]); therefore,
the held-out Brier improvement is a favorable point estimate but is not supported
at the declared 95% level.

The static frozen-DINOv2 fused control achieved stronger downstream point
estimates than the DINO-WM predicted-future head: Brier 0.1430 and all-target MSE
0.03725. No prospective direct interval between those two models was registered,
so this comparison is descriptive. It shows that the learned dynamics are valid
and action-sensitive, while the downstream advantage over a static visual
representation is not established by this benchmark.

## Scope

These results support a controlled simulator-domain integration claim and show
that the learned transition predicts future spatial features better than static
or action-shuffled controls. They do not establish field-video generalization,
operational safety, cross-domain effectiveness, or superiority to static DINOv2
for Flood-SAR outcomes.

The exact machine-readable records are the
[`development confirmation report`](DINOWM_DEVELOPMENT_CONFIRMATION_REPORT.json),
[`held-out report`](DINOWM_HELDOUT_REPORT.json), and
[`test-freeze manifest`](DINOWM_TEST_FREEZE_MANIFEST.json). Their integrity
digests are recorded in [`DINOWM_REPORTS.sha256`](DINOWM_REPORTS.sha256).
