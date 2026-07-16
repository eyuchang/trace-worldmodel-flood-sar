const pptxgen = require('pptxgenjs');
const {
  imageSizingCrop,
  imageSizingContain,
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
  codeToRuns,
} = require('/home/oai/skills/slides/pptxgenjs_helpers');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'TRACE-JEPA teaching project';
pptx.subject = 'Flood search-and-rescue implementation tutorial';
pptx.title = 'TRACE-JEPA Flood Rescue Implementation: Emergency Call to Authorized Rescue';
pptx.company = 'TRACE-JEPA';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Aptos Display',
  bodyFontFace: 'Aptos',
  lang: 'en-US',
};
pptx.defineLayout({ name: 'LAYOUT_WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'LAYOUT_WIDE';
pptx.margin = 0;

const W = 13.333;
const H = 7.5;
const COLORS = {
  bg: 'F8FAFC',
  ink: '0F172A',
  muted: '475569',
  blue: '1D4ED8',
  blue2: 'DBEAFE',
  cyan: '0891B2',
  teal: '0F766E',
  green: '15803D',
  orange: 'EA580C',
  red: 'B91C1C',
  purple: '6D28D9',
  line: 'CBD5E1',
  codeBg: '111827',
  codeFg: 'E5E7EB',
  yellow: 'FEF3C7',
};

function addTitle(slide, title, subtitle) {
  slide.background = { color: COLORS.bg };
  slide.addText(title, {
    x: 0.45, y: 0.32, w: 12.45, h: 0.48,
    fontFace: 'Aptos Display', fontSize: 28, bold: true, color: COLORS.ink,
    margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.47, y: 0.86, w: 11.8, h: 0.28,
      fontSize: 10.5, color: COLORS.muted, margin: 0,
    });
  }
}

function addFooter(slide, slideNo, note) {
  slide.addText(`TRACE-JEPA flood rescue tutorial · ${slideNo}`, {
    x: 0.45, y: 7.18, w: 3.5, h: 0.18,
    fontSize: 7.5, color: '64748B', margin: 0,
  });
  if (note) {
    slide.addText(note, {
      x: 6.6, y: 7.18, w: 6.2, h: 0.18,
      fontSize: 7.5, color: '64748B', align: 'right', margin: 0,
    });
  }
}

function addSectionTag(slide, text, color = COLORS.blue) {
  // Stage tags are intentionally omitted from the visible slide.
  // They are kept as call sites so slide code remains easy to scan.
}


function addTextBox(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontSize: opts.fontSize || 13,
    color: opts.color || COLORS.ink,
    bold: opts.bold || false,
    valign: opts.valign || 'mid',
    margin: opts.margin || 0.06,
    breakLine: false,
    fit: 'shrink',
    fill: opts.fill ? { color: opts.fill, transparency: opts.transparency ?? 0 } : undefined,
    line: opts.line ? { color: opts.line, width: 1 } : undefined,
    radius: opts.radius || 0.12,
  });
}

function bulletText(items) {
  return items.map(t => `• ${t}`).join('\n');
}

function addBullets(slide, items, x, y, w, h, opts = {}) {
  slide.addText(bulletText(items), {
    x, y, w, h,
    fontSize: opts.fontSize || 12.5,
    color: opts.color || COLORS.ink,
    margin: opts.margin || 0.08,
    breakLine: false,
    fit: 'shrink',
    valign: opts.valign || 'top',
    paraSpaceAfterPt: 4,
    fill: opts.fill ? { color: opts.fill, transparency: opts.transparency ?? 0 } : undefined,
    line: opts.line ? { color: opts.line, width: 1 } : undefined,
  });
}

function addCode(slide, code, lang, x, y, w, h, fontSize = 8.5) {
  const runs = codeToRuns(code.trim(), lang).map(r => ({
    text: r.text,
    options: { ...r.options, fontSize, fontFace: 'Consolas' },
  }));
  slide.addText(runs, {
    x, y, w, h,
    margin: 0.08,
    fit: 'shrink',
    valign: 'top',
    fill: { color: COLORS.codeBg },
    line: { color: '334155', width: 1 },
  });
}

function addPlainCode(slide, code, x, y, w, h, fontSize = 9) {
  slide.addText(code.trim(), {
    x, y, w, h,
    fontFace: 'Courier New',
    fontSize,
    color: COLORS.codeFg,
    margin: 0.12,
    fit: 'shrink',
    valign: 'top',
    breakLine: false,
    fill: { color: COLORS.codeBg },
    line: { color: '334155', width: 1 },
  });
}

function addMiniCard(slide, heading, body, x, y, w, h, color = COLORS.blue) {
  slide.addText([{text: heading + '\n', options: {bold: true, color}}, {text: body, options: {color: COLORS.ink}}], {
    x, y, w, h,
    fontSize: 12,
    margin: 0.12,
    valign: 'top',
    fit: 'shrink',
    fill: { color: 'FFFFFF' },
    line: { color: COLORS.line, width: 1 },
  });
}

function addStagePill(slide, text, x, y, color) {
  slide.addText(text, {
    x, y, w: 1.38, h: 0.30,
    fontSize: 9.5,
    bold: true,
    color: 'FFFFFF',
    align: 'center',
    valign: 'mid',
    margin: 0.02,
    fill: { color },
    line: { color },
    radius: 0.15,
  });
}

function finalChecks() {
  for (const s of pptx._slides) {
    warnIfSlideHasOverlaps(s, pptx, { ignoreLines: true, ignoreDecorativeShapes: true, muteContainment: true });
    warnIfSlideElementsOutOfBounds(s, pptx);
  }
}

const asset = (p) => `docs/tutorial_deck/assets/${p}`;

// Slide 1
{
  const slide = pptx.addSlide();
  slide.background = { color: '0B1220' };
  slide.addImage({ path: asset('flood_rescue_cover_16x9.png'), x: 0, y: 0, w: W, h: H });
  slide.addText('TRACE-JEPA Flood Rescue Implementation', {
    x: 0.55, y: 0.46, w: 8.8, h: 0.55,
    fontFace: 'Aptos Display', fontSize: 31, bold: true, color: 'FFFFFF',
    margin: 0,
  });
  slide.addText('Stages 0-6 · emergency call, mission grounding, TRACE gate, verification, revision, rescue', {
    x: 0.58, y: 1.05, w: 9.8, h: 0.34,
    fontSize: 12.5, color: 'E2E8F0', margin: 0,
  });
  slide.addText('Teaching rule: build the accountability path before downloading JEPA.', {
    x: 0.58, y: 6.75, w: 8.8, h: 0.28,
    fontSize: 13, bold: true, color: 'FFFFFF', margin: 0.02,
    fill: { color: '0F172A', transparency: 20 },
  });
}

// Slide 2
{
  const slide = pptx.addSlide();
  addTitle(slide, 'What this demo is about', 'One central controller, two physical agents, one human authority role, one simulated flood world.');
  addSectionTag(slide, 'Mission story');
  addMiniCard(slide, 'Goal', 'Four residents are isolated at Riverside Apartments. A rescue boat must reach them within 20 minutes.', 0.6, 1.62, 3.75, 1.15, COLORS.blue);
  addMiniCard(slide, 'Conflict', 'The North Channel is shorter but unverified. The South Detour is slower but reported open.', 4.62, 1.62, 3.75, 1.15, COLORS.orange);
  addMiniCard(slide, 'Hidden truth', 'Simulation ground truth contains debris in the North Channel. Mission Control cannot use this until the drone observes it.', 8.65, 1.62, 3.95, 1.15, COLORS.red);
  addBullets(slide, [
    'Planner proposes structurally possible actions.',
    'World Model predicts consequences for each candidate.',
    'TRACE Gate decides whether the prediction may authorize the action.',
    'Incident Commander remains the authority for high-stakes dispatch.'
  ], 0.8, 3.15, 5.0, 2.4, {fontSize: 14, fill: 'FFFFFF', line: COLORS.line});
  slide.addImage({ path: asset('operational_cast.png'), ...imageSizingContain(asset('operational_cast.png'), 6.2, 3.0, 6.5, 3.35) });
  addFooter(slide, 2, 'Read: docs/MISSION_BRIEF.md');
}

// Slide 3
{
  const slide = pptx.addSlide();
  addTitle(slide, 'The operational cast is fixed before code', 'Avoid ambiguous “evaluator” or “rescue system” language. Use these nouns.');
  addSectionTag(slide, 'Stage 0');
  slide.addImage({ path: asset('operational_cast.png'), ...imageSizingContain(asset('operational_cast.png'), 0.65, 1.45, 6.0, 5.1) });
  addBullets(slide, [
    'Flood Environment owns hidden truth and emits observations/outcomes.',
    'Survey Drone observes a requested route and reports back.',
    'Rescue Boat executes only authorized rescue dispatches.',
    'Mission Controller is one program: state, planner, world model, TRACE gate, dispatcher.',
    'Incident Commander supplies external authority; TRACE cannot synthesize it.'
  ], 7.0, 1.55, 5.55, 4.25, {fontSize: 13.5, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Operational evaluator? No. Offline evaluation scores logs after the run and sends no commands.', 7.0, 6.05, 5.55, 0.55, {fontSize: 12.5, bold: true, fill: COLORS.yellow, line: 'F59E0B'});
  addFooter(slide, 3, 'Side file S08 maps names to source files');
}

// Slide 4
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage map for the first implementation block', 'Each stage has a concrete observable exit condition.');
  const stages = [
    ['0', 'Briefing', 'Name entities and knowledge boundary'],
    ['1', 'Install', 'Verifier and tests pass'],
    ['2', 'Visualize', 'Render Mission Control view vs hidden truth'],
    ['3', 'Scenario + actions', 'Every action is grounded'],
    ['4', 'Contracts', 'Evidence and TRACE records round-trip'],
    ['5', 'Policy gate', 'High confidence cannot override failed support gates'],
    ['6', 'Mock loop', 'Hold north, verify, revise, clear south'],
  ];
  let y = 1.35;
  stages.forEach((r, i) => {
    const color = [COLORS.teal, COLORS.blue, COLORS.purple, COLORS.orange, COLORS.green, COLORS.red, COLORS.cyan][i];
    addStagePill(slide, `Stage ${r[0]}`, 0.72, y, color);
    slide.addText(r[1], {x: 2.25, y: y, w: 2.3, h: 0.3, fontSize: 13, bold: true, color: COLORS.ink, margin: 0});
    slide.addText(r[2], {x: 4.55, y: y, w: 7.2, h: 0.3, fontSize: 12.5, color: COLORS.muted, margin: 0});
    y += 0.72;
  });
  addTextBox(slide, 'This deck documents the call-to-rescue path directly and gives carefully labeled side files for long code.', 0.72, 6.65, 11.8, 0.36, {fontSize: 12, fill: 'FFFFFF', line: COLORS.line});
  addFooter(slide, 4, 'Deck + side files live in docs/tutorial_deck/');
}

// Slide 5
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 1: laptop-safe install', 'No PyTorch, no V-JEPA checkpoint, no GPU required yet.');
  addSectionTag(slide, 'Install code');
  addCode(slide, `# Side file S00_environment_setup.sh
git --version
uname -m
conda info | grep platform

conda create -n trace-jepa python=3.12 pip -y
conda activate trace-jepa
python --version
which python`, 'bash', 0.7, 1.45, 5.8, 2.45, 10);
  addCode(slide, `# Side file S01_install_and_verify.sh
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
trace-jepa-verify
pytest`, 'bash', 0.7, 4.25, 5.8, 1.45, 10);
  addBullets(slide, [
    'Expected: Python 3.12.x inside the trace-jepa environment.',
    'Expected: verifier passes and core tests pass.',
    'Acceptable: optional V-JEPA/PyTorch test skipped.',
    'Do not install .[jepa] yet.'
  ], 7.05, 1.55, 5.45, 3.0, {fontSize: 14, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Exit condition: project commands are available and the core test suite passes.', 7.05, 5.0, 5.45, 0.55, {fontSize: 13, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addFooter(slide, 5, 'Side files S00-S01');
}

// Slide 6
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 2: visualize before writing more code', 'The map forces every action and observation to refer to a concrete place.');
  addSectionTag(slide, 'Visual code');
  addCode(slide, `# Side file S02_visualize_environment.sh
trace-jepa-visualize \
  --scenario configs/scenarios/riverside_flood_v1.yaml \
  --output artifacts/runs/scenario_brief

open artifacts/runs/scenario_brief/operational_cast.svg
open artifacts/runs/scenario_brief/mission_controller_knowledge.svg
open artifacts/runs/scenario_brief/simulation_ground_truth.svg`, 'bash', 0.65, 1.38, 5.8, 2.75, 9);
  addBullets(slide, [
    'The visualizer reads one scenario file.',
    'It renders vector SVGs, not raster-only screenshots.',
    'The same world is shown from two information states.',
    'The hidden truth view is for debugging and evaluation only.'
  ], 0.65, 4.55, 5.8, 1.55, {fontSize: 12.5, fill: 'FFFFFF', line: COLORS.line});
  slide.addImage({ path: asset('mission_controller_knowledge.png'), ...imageSizingContain(asset('mission_controller_knowledge.png'), 6.82, 1.35, 2.95, 2.35) });
  slide.addImage({ path: asset('simulation_ground_truth.png'), ...imageSizingContain(asset('simulation_ground_truth.png'), 9.86, 1.35, 2.95, 2.35) });
  addTextBox(slide, 'Mission Controller knowledge: North Channel unverified', 6.82, 3.85, 2.95, 0.44, {fontSize: 10, bold: true, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Simulation ground truth: North Channel blocked', 9.86, 3.85, 2.95, 0.44, {fontSize: 10, bold: true, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Never leak simulation ground truth into Mission State.', 7.05, 5.1, 5.3, 0.55, {fontSize: 14, bold: true, color: COLORS.red, fill: 'FEE2E2', line: COLORS.red});
  addFooter(slide, 6, 'Side file S02');
}

// Slide 7
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 2: the two map views answer different questions', 'The visual difference is the first safety boundary.');
  addSectionTag(slide, 'Knowledge boundary');
  slide.addImage({ path: asset('mission_controller_knowledge.png'), ...imageSizingContain(asset('mission_controller_knowledge.png'), 0.65, 1.45, 5.95, 4.7) });
  slide.addImage({ path: asset('simulation_ground_truth.png'), ...imageSizingContain(asset('simulation_ground_truth.png'), 6.75, 1.45, 5.95, 4.7) });
  addTextBox(slide, 'Input to Mission Controller', 1.1, 6.25, 5.0, 0.35, {fontSize: 12.5, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addTextBox(slide, 'Used only for labels, outcomes, and offline scoring', 7.2, 6.25, 5.0, 0.35, {fontSize: 12.5, bold: true, fill: 'FEE2E2', line: COLORS.red});
  addFooter(slide, 7, 'View names replace “agent/evaluator” ambiguity');
}

// Slide 8
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 3: scenario YAML grounds the mission', 'Routes carry both what is observed and what is true in the simulator.');
  addSectionTag(slide, 'Scenario code');
  addCode(slide, `# Side file S03_riverside_flood_v1.yaml
routes:
  north_channel:
    label: North Channel
    waypoints: [[12,16], [24,33], [42,51], [60,64], [78,70], [88,66]]
    truth_status: blocked
    blockage_position: [60,64]
    observed_status: unknown

  south_detour:
    label: South Detour
    waypoints: [[12,16], [30,12], [52,18], [72,34], [84,52], [88,66]]
    truth_status: open
    observed_status: open`, 'yaml', 0.65, 1.40, 6.2, 4.15, 8);
  addBullets(slide, [
    'truth_status is owned by the Flood Environment.',
    'observed_status is what the Mission Controller can use.',
    'The North Channel starts unknown, not blocked, from the controller’s view.',
    'The drone changes observed_status only after verification.'
  ], 7.15, 1.55, 5.35, 2.95, {fontSize: 13, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Exit condition: you can explain why the same route has two statuses.', 7.15, 5.05, 5.35, 0.55, {fontSize: 13, bold: true, fill: COLORS.yellow, line: 'F59E0B'});
  addFooter(slide, 8, 'Side file S03');
}

// Slide 9
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 3: actions are grounded, not strings', 'The same action object is read by the planner, predictor, TRACE record, dispatcher, environment, and audit.');
  addSectionTag(slide, 'Action code');
  addCode(slide, `# Side file S04_flood_actions_v1.yaml
actions:
  dispatch_rescue_boat:
    requires_authority: true
    reversible: false
    parameters: [origin, destination, route_id, people_count, deadline_s]

  verify_route:
    requires_authority: false
    reversible: true
    parameters: [route_id, purpose]`, 'yaml', 0.65, 1.35, 6.0, 2.9, 9);
  addCode(slide, `# Grounded ActionInstance shape
action_type: dispatch_rescue_boat
actor_id: rescue_boat_1
origin: rescue_base
destination: riverside_apartments
route_id: south_detour
parameters:
  people_count: 4
  deadline_s: 1200`, 'yaml', 7.0, 1.35, 5.55, 2.9, 9);
  addTextBox(slide, 'Bad: "dispatch_boat_north". Good: actor + route + origin + destination + mission parameters.', 0.9, 4.75, 11.7, 0.5, {fontSize: 14, bold: true, fill: 'FFFFFF', line: COLORS.line});
  addBullets(slide, [
    'The action object becomes part of the commitment and later evidence chain.',
    'Every durable dispatch must cite the authorizing record version.',
    'This is the first step toward plan-branch localization.'
  ], 1.1, 5.55, 11.0, 1.0, {fontSize: 12.5});
  addFooter(slide, 9, 'Side file S04');
}

// Slide 10
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 4: durable contracts before model code', 'Freeze what will be stored before building the predictor.');
  addSectionTag(slide, 'Contract code');
  addCode(slide, `# Source: src/trace_jepa/contracts/models.py
class WorldModelEvidence(FrozenModel):
    evidence_id: str
    encoder_version: str
    predictor_version: str
    candidate_plan_id: str
    rollout_horizon: int
    predicted_claims: tuple[str, ...]
    uncertainty: float
    model_support: float
    out_of_distribution_score: float
    realized_outcome: dict | None = None

class TraceRecord(FrozenModel):
    record_id: str
    record_version: int
    policy_version: str
    claim: Claim
    evidence_refs: tuple[str, ...]
    final_status: TraceStatus
    failed_gates: tuple[str, ...]
    missing_items: tuple[str, ...]
    repair: str | None
    consumer_actions: tuple[ConsumerAction, ...]`, 'python', 0.65, 1.38, 6.35, 4.65, 7.0);
  addBullets(slide, [
    'Evidence states what a model version predicted.',
    'TraceRecord states what claim was evaluated and why it passed or failed.',
    'ConsumerAction records what the Mission Controller did with the verdict.',
    'Revisions create new versions; committed records are not edited in place.'
  ], 7.28, 1.6, 5.2, 3.25, {fontSize: 13, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Long code is in complete_source/S04_contracts_models.py', 7.28, 5.2, 5.2, 0.5, {fontSize: 12.5, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addFooter(slide, 10, 'Side file complete_source/S04');
}

// Slide 11
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 4: first TRACE record by hand', 'This validates storage and the confidence/support distinction before any automatic policy logic.');
  addSectionTag(slide, 'Lab script S05');
  addCode(slide, `# Side file S05_first_trace_record.py
evidence = WorldModelEvidence(
    candidate_plan_id="north-direct",
    predicted_claims=("North Channel is open for dispatch.",),
    uncertainty=0.08,
    model_support=0.28,
    out_of_distribution_score=0.82,
    rollout_horizon=3,
)

claim = Claim(
    layer=ClaimLayer.PREDICTIVE,
    text="North Channel is open for dispatch.",
    confidence=0.92,
)

record = TraceRecord(
    final_status=TraceStatus.DEFER,
    failed_gates=("model_support", "out_of_distribution"),
    missing_items=("A current observation of North Channel.",),
    repair="Send the survey drone before dispatching the boat.",
)`, 'python', 0.65, 1.38, 6.35, 4.85, 7.0);
  addCode(slide, `$ PYTHONPATH=src python labs/01_contracts_and_log/first_record.py
Evidence stored: wm-evidence-lab01-north-route-v1
Predicted plan success: 0.92
Claim confidence: 0.92
Evidence support/OOD: 0.28 / 0.82
TRACE status: defer
Failed gates: model_support, out_of_distribution
Hash chain valid: True
Records in repository: 1`, 'bash', 7.25, 1.38, 5.3, 2.6, 8.2);
  addTextBox(slide, 'Run it twice. Records in repository must remain 1.', 7.25, 4.35, 5.3, 0.48, {fontSize: 13, bold: true, fill: COLORS.yellow, line: 'F59E0B'});
  addBullets(slide, [
    '0.92 is printed so students see the number.',
    'Support and OOD still determine whether the claim can authorize action.',
    'The hand-authored record is only a contract/storage exercise.'
  ], 7.25, 5.05, 5.3, 1.2, {fontSize: 11.8});
  addFooter(slide, 11, 'Side file lab_scripts/S05');
}

// Slide 12
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 5: policy gate computes the verdict', 'The next step removes manual judgment from the first record.');
  addSectionTag(slide, 'Policy code');
  addCode(slide, `# configs/policies/trace_v1.yaml
policy_version: trace-flood-v1
min_model_support: 0.60
max_ood_score: 0.35
max_uncertainty: 0.30
max_rollout_horizon: 8
max_observation_age_s: 120.0
allow_qualified_reversible_probe: true
require_authority_for:
  - dispatch_rescue_boat
  - deploy_ground_team`, 'yaml', 0.65, 1.35, 5.6, 3.25, 9.2);
  addCode(slide, `# Source: src/trace_jepa/runtime/policy.py
if evidence.model_support < min_model_support:
    failed.append("model_support")
if evidence.out_of_distribution_score > max_ood_score:
    failed.append("out_of_distribution")

if authority_required and not authority_present:
    return ESCALATE

if failed and reversible:
    return QUALIFY
if failed:
    return HOLD
return CLEAR`, 'python', 6.65, 1.35, 5.95, 3.25, 8.2);
  addTextBox(slide, 'Hard gates are lexicographic: a high utility score cannot average away failed support or OOD gates.', 1.1, 5.02, 11.2, 0.52, {fontSize: 14, bold: true, fill: 'FEE2E2', line: COLORS.red, color: COLORS.red});
  addFooter(slide, 12, 'Side file S06 + complete_source/S06_runtime_policy.py');
}

// Slide 13
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 5: four policy cases students should predict', 'This is a deterministic test fixture, not an experiment.');
  addSectionTag(slide, 'Expected output');
  addTextBox(slide, 'Case 1 · support 0.28 / OOD 0.82 · dispatch boat · authority yes → HOLD', 0.75, 1.45, 11.85, 0.42, {fontSize: 12.2, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Case 2 · support 0.28 / OOD 0.82 · verify route · authority no → QUALIFY', 0.75, 1.95, 11.85, 0.42, {fontSize: 12.2, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Case 3 · support 0.90 / OOD 0.10 · dispatch boat · authority no → ESCALATE', 0.75, 2.45, 11.85, 0.42, {fontSize: 12.2, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Case 4 · support 0.90 / OOD 0.10 · dispatch boat · authority yes → CLEAR', 0.75, 2.95, 11.85, 0.42, {fontSize: 12.2, fill: 'FFFFFF', line: COLORS.line});
  addCode(slide, `$ PYTHONPATH=src python labs/01_contracts_and_log/policy_walkthrough.py
Case 1: Unsupported irreversible dispatch -> hold
Case 2: Unsupported but reversible verification -> qualify
Case 3: Supported dispatch without authority -> escalate
Case 4: Supported dispatch with authority -> clear`, 'bash', 1.0, 4.25, 11.35, 1.3, 9);
  addTextBox(slide, 'Teaching point: TRACE is not anti-action. It holds the risky commitment but allows evidence gathering.', 1.0, 5.9, 11.3, 0.44, {fontSize: 13.5, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addFooter(slide, 13, 'Side file lab_scripts/S06');
}

// Slide 14
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Stage 6 preview: run the closed-loop demo', 'Now the Mission Controller connects planner, predictor, TRACE gate, dispatcher, environment, and revision.');
  addSectionTag(slide, 'Demo code');
  addCode(slide, `# Side file S07_run_mock_closed_loop.sh
trace-jepa-demo --output artifacts/runs/deck_walkthrough
cat artifacts/runs/deck_walkthrough/summary.json
find artifacts/runs/deck_walkthrough -maxdepth 3 -type f | sort`, 'bash', 0.75, 1.35, 5.65, 1.75, 9.5);
  addBullets(slide, [
    'North dispatch proposed: high success, low support, high OOD.',
    'TRACE holds the irreversible northern dispatch.',
    'TRACE qualifies or clears bounded drone verification.',
    'Drone observes debris and reports North Channel blocked.',
    'Revision rejects the northern route claim append-only.',
    'Planner repairs only the dependent route branch.',
    'South Detour dispatch clears with authority.'
  ], 6.85, 1.25, 5.55, 4.65, {fontSize: 12.5, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Exit condition: no rescue commitment exists without an authorizing record version.', 0.75, 3.62, 5.65, 0.72, {fontSize: 13, bold: true, fill: COLORS.yellow, line: 'F59E0B'});
  addFooter(slide, 14, 'Side file S07');
}

// Slide 15
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Where the long code lives', 'The deck stays teachable; the side files remain complete and inspectable.');
  addSectionTag(slide, 'Side-file index');
  addCode(slide, `Label  File                                      Purpose
S00    S00_environment_setup.sh                Conda/Python setup
S01    S01_install_and_verify.sh               Editable install and tests
S02    S02_visualize_environment.sh            Render operational cast and maps
S03    S03_riverside_flood_v1.yaml             Scenario geometry + route status
S04    S04_flood_actions_v1.yaml               Grounded action schema
S05    lab_scripts/S05_first_trace_record.py   First TRACE record
S06    lab_scripts/S06_policy_walkthrough.py   Automatic gate cases
S07    S07_run_mock_closed_loop.sh             Pre-filled deterministic episode
S08    S08_core_source_file_map.md             Core source map
S09    S09_emergency_call.txt                  Example call input
S10    S10_run_emergency_call.sh               Call-to-rescue command
S10-13 complete_source/                        Intake, CLI, timeline, controller`, 'text', 0.75, 1.35, 11.9, 4.7, 8.2);
  addTextBox(slide, 'Complete source copies are in side_files/complete_source/. Treat them as read-only references.', 1.05, 6.25, 11.1, 0.42, {fontSize: 12.5, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addFooter(slide, 15, 'docs/tutorial_deck/side_files/README.md');
}

// Slide 16
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Next live coding checkpoint', 'After students can explain the cast and run the first scripts, resume at the policy walkthrough.');
  addSectionTag(slide, 'Resume here');
  addBullets(slide, [
    'Run S05 and explain why confidence = 0.92 is not permission.',
    'Run S06 and predict all four policy outcomes before executing it.',
    'Render the two map views and identify which one Mission Control may use.',
    'Run S07 and inspect the record log, evidence folder, commitments log, and summary.',
    'Only after the mock loop works do we install PyTorch and cache V-JEPA features.'
  ], 0.85, 1.45, 6.0, 3.45, {fontSize: 14, fill: 'FFFFFF', line: COLORS.line});
  slide.addImage({ path: asset('flood_rescue_cover_16x9.png'), x: 7.1, y: 1.35, w: 5.35, h: 3.01 });
  addTextBox(slide, 'Teaching mantra: predicted future → typed claim → TRACE record → permitted action → realized outcome → revision.', 0.95, 5.45, 11.55, 0.6, {fontSize: 14, bold: true, fill: COLORS.yellow, line: 'F59E0B'});
  addFooter(slide, 16, 'Next: close the mock loop, then replace mock visual features');
}


// Slide 17
{
  const slide = pptx.addSlide();
  addTitle(slide, 'The operational input is an emergency call', 'The call grounds the incident. It does not contain hidden route truth.');
  addSectionTag(slide, 'Call intake');
  addTextBox(slide, 'Emergency phone report', 0.72, 1.35, 5.75, 0.42, {fontSize: 14, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addCode(slide, `Emergency. Four residents are stranded at
Riverside Apartments. Flood water is rising
and the road is inaccessible.`, 'text', 0.72, 1.95, 5.75, 1.55, 13);
  addTextBox(slide, 'Normalized EmergencyCall', 6.85, 1.35, 5.75, 0.42, {fontSize: 14, bold: true, fill: 'ECFDF5', line: COLORS.green});
  addCode(slide, `raw_text: preserved verbatim
reported_location: Riverside Apartments
normalized_location_id: riverside_apartments
people_count: 4
deadline_s: 1200
source: emergency_phone`, 'yaml', 6.85, 1.95, 5.75, 2.15, 10.5);
  addTextBox(slide, 'The intake parser may extract location and people count. It may not infer “North Channel is blocked.” That fact belongs to simulation ground truth until observed.', 0.9, 4.75, 11.55, 0.78, {fontSize: 13.2, bold: true, fill: 'FEE2E2', line: COLORS.red, color: COLORS.red});
  addTextBox(slide, 'Side input S09 · full parser complete_source/S10_emergency_call_intake.py', 1.15, 6.0, 11.0, 0.42, {fontSize: 12.5, fill: 'FFFFFF', line: COLORS.line});
  addFooter(slide, 17, 'EmergencyCall is a durable typed input');
}

// Slide 18
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Run from the call and watch actions live', 'The new command prints every decision and writes an inspectable run directory.');
  addSectionTag(slide, 'Run command');
  addPlainCode(slide, `# File input
trace-jepa-call --call-file examples/calls/riverside_call.txt
                --output artifacts/runs/call_001

# Inline equivalent
trace-jepa-call --call "Four residents at Riverside Apartments."
                --output artifacts/runs/call_002`, 0.72, 1.35, 7.25, 2.95, 10.0);
  addBullets(slide, [
    'If the text is ambiguous, add --location and --people.',
    'The location must match the teaching scenario registry.',
    'A later geocoder can replace the resolver without changing the record contract.',
    'Use a new output folder for each run.'
  ], 8.3, 1.45, 4.35, 2.75, {fontSize: 12.5, fill: 'FFFFFF', line: COLORS.line});
  addPlainCode(slide, `# Inspect results on macOS
cat artifacts/runs/call_001/timeline.txt
open artifacts/runs/call_001/figures/mission_controller_knowledge.svg
open artifacts/runs/call_001/figures/action_timeline.svg`, 1.0, 4.85, 11.35, 1.2, 10.0);
  addFooter(slide, 18, 'Side file S10_run_emergency_call.sh');
}

// Slide 19
{
  const slide = pptx.addSlide();
  addTitle(slide, 'What you should see after the call', 'The call is followed by assessment, evidence gathering, revision, local repair, and rescue.');
  addSectionTag(slide, 'Live timeline');
  addBullets(slide, [
    'North dispatch: HOLD because support is low and OOD is high.',
    'Drone verification: CLEAR as a bounded information action.',
    'Drone reports North Channel blocked.',
    'TRACE appends a rejecting revision to the north-route claim.',
    'Planner repairs only the route-dependent branch.',
    'South Detour: CLEAR with Incident Commander authority.',
    'Boat reaches four residents; record chain verifies.'
  ], 0.7, 1.35, 5.3, 4.65, {fontSize: 12.5, fill: 'FFFFFF', line: COLORS.line});
  slide.addImage({ path: asset('emergency_action_timeline.png'), ...imageSizingContain(asset('emergency_action_timeline.png'), 6.35, 1.25, 6.2, 5.65) });
  addFooter(slide, 19, 'Generated from summary.timeline');
}

// Slide 20
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Code path: call text to Mission Controller', 'Short snippets stay on the slide; full source is in labeled side files.');
  addSectionTag(slide, 'Code map');
  addCode(slide, `call = EmergencyCallIntake(environment.scenario).parse(
    call_text,
    location=args.location,
    people=args.people,
)
environment.register_emergency_call(call)
controller = MissionController(environment=environment, runtime=runtime)
summary = controller.run_episode(output, event_sink=print_event)`, 'python', 0.65, 1.35, 6.2, 3.05, 8.6);
  addMiniCard(slide, 'S10', 'intake.py\nGround location and people count; preserve raw call.', 7.15, 1.35, 2.55, 1.15, COLORS.blue);
  addMiniCard(slide, 'S11', 'emergency_cli.py\nTerminal arguments, call file, output directory.', 9.95, 1.35, 2.55, 1.15, COLORS.teal);
  addMiniCard(slide, 'S12', 'reporting.py\nWrite timeline.txt and action_timeline.svg.', 7.15, 2.8, 2.55, 1.15, COLORS.purple);
  addMiniCard(slide, 'S13', 'controller.py\nEmit each subsequent action and record transition.', 9.95, 2.8, 2.55, 1.15, COLORS.orange);
  addTextBox(slide, 'Test: tests/test_emergency_call.py verifies location parsing, first action = drone verification, final action = South Detour, and rescue success.', 0.85, 5.15, 11.65, 0.72, {fontSize: 13, bold: true, fill: COLORS.yellow, line: 'F59E0B'});
  addFooter(slide, 20, 'Full code: side_files/complete_source/S10-S13');
}

// Slide 21
{
  const slide = pptx.addSlide();
  addTitle(slide, 'Your next terminal checkpoint', 'Update the editable install, run one call, and open the action timeline.');
  addSectionTag(slide, 'Do this now');
  addPlainCode(slide, `cd ~/Projects/trace_jepa_flood_sar_starter
conda activate trace-jepa
python -m pip install -e ".[dev]"
pytest

trace-jepa-call --call-file examples/calls/riverside_call.txt
                --output artifacts/runs/call_001

open artifacts/runs/call_001/figures/action_timeline.svg`, 0.8, 1.35, 7.2, 4.35, 10.0);
  addBullets(slide, [
    'Expected tests: all core tests pass.',
    'Expected first selected action: survey_drone_1 verifies north_channel.',
    'Expected final selected action: rescue_boat_1 uses south_detour.',
    'Expected final outcome: four residents reached.',
    'Expected repository verification: true.'
  ], 8.35, 1.55, 4.2, 3.65, {fontSize: 13, fill: 'FFFFFF', line: COLORS.line});
  addTextBox(slide, 'Do not install JEPA yet. First understand every line of the call-to-rescue path.', 8.35, 5.55, 4.2, 0.68, {fontSize: 13, bold: true, fill: COLORS.blue2, line: COLORS.blue});
  addFooter(slide, 21, 'Next: replace mock visual features only after this passes');
}

finalChecks();
pptx.writeFile({ fileName: 'docs/tutorial_deck/TRACE_JEPA_Flood_Rescue_Tutorial_Emergency_Call.pptx' });
