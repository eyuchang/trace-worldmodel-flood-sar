const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');
const {
  imageSizingCrop,
  imageSizingContain,
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
  codeToRuns,
} = require('/home/oai/skills/slides/pptxgenjs_helpers');

const ROOT = path.resolve(__dirname, '../..');
const ASSET = (name) => path.join(__dirname, 'assets', name);
const SIDE = (name) => path.join(__dirname, 'side_files', name);
const SRC = (name) => path.join(ROOT, name);

const pptx = new pptxgen();
pptx.defineLayout({ name: 'WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'WIDE';
pptx.author = 'Edward Y. Chang';
pptx.subject = 'Faithful eight-step implementation walkthrough for TRACE-WorldModel flood search-and-rescue';
pptx.title = 'Closing the Loop: Flood-SAR Implementation in Eight Verified Steps';
pptx.company = 'Stanford University';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Aptos Display',
  bodyFontFace: 'Aptos',
  lang: 'en-US',
};
pptx.margin = 0;

const W = 13.333;
const H = 7.5;
const C = {
  bg: 'F8FAFC', ink: '0F172A', muted: '475569', line: 'CBD5E1',
  blue: '1D4ED8', blueLight: 'DBEAFE', navy: '0B1F3A',
  teal: '0F766E', cyan: '0891B2', green: '15803D', greenLight: 'DCFCE7',
  orange: 'EA580C', orangeLight: 'FFEDD5', red: 'B91C1C', redLight: 'FEE2E2',
  purple: '6D28D9', purpleLight: 'EDE9FE', yellow: 'FEF3C7',
  codeBg: '111827', codeFg: 'E5E7EB', white: 'FFFFFF', slate: '64748B',
};

function readLines(file, start, end) {
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
  return lines.slice(start - 1, end).join('\n');
}

function title(slide, text, subtitle) {
  slide.background = { color: C.bg };
  slide.addText(text, {
    x: 0.45, y: 0.28, w: 12.35, h: 0.5,
    fontFace: 'Aptos Display', fontSize: 27, bold: true, color: C.ink, margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.47, y: 0.82, w: 12.0, h: 0.32,
      fontSize: 10.5, color: C.muted, margin: 0,
    });
  }
  slide.addShape(pptx.ShapeType.line, { x: 0.45, y: 1.18, w: 12.35, h: 0, line: { color: C.line, width: 1 } });
}

function footer(slide, n, note='') {
  slide.addText(`TRACE-WorldModel Flood-SAR · ${n}`, { x: 0.45, y: 7.18, w: 3.3, h: 0.18, fontSize: 7.5, color: C.slate, margin: 0 });
  if (note) slide.addText(note, { x: 6.2, y: 7.18, w: 6.6, h: 0.18, fontSize: 7.5, color: C.slate, align: 'right', margin: 0 });
}

function stepBadge(slide, n, label, color=C.blue) {
  slide.addText(`STEP ${n}`, { x: 0.52, y: 1.34, w: 1.0, h: 0.34, fontSize: 10, bold: true, color: C.white, align: 'center', valign: 'mid', margin: 0, fill: { color }, line: { color }, radius: 0.14 });
  slide.addText(label, { x: 1.68, y: 1.34, w: 5.7, h: 0.34, fontSize: 13, bold: true, color, margin: 0.01 });
}

function box(slide, x, y, w, h, fill='FFFFFF', line=C.line, radius=0.1) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h, rectRadius: radius, fill: { color: fill }, line: { color: line, width: 1 } });
}

function text(slide, value, x, y, w, h, opts={}) {
  slide.addText(value, {
    x, y, w, h, fontSize: opts.fontSize || 12.5, color: opts.color || C.ink,
    bold: opts.bold || false, margin: opts.margin ?? 0.08, valign: opts.valign || 'top',
    fit: 'shrink', align: opts.align || 'left', breakLine: false,
    fill: opts.fill ? { color: opts.fill, transparency: opts.transparency || 0 } : undefined,
    line: opts.line ? { color: opts.line, width: 1 } : undefined,
  });
}

function bullets(slide, items, x, y, w, h, opts={}) {
  const runs = [];
  items.forEach((item, i) => {
    runs.push({ text: `• ${item}${i < items.length - 1 ? '\n' : ''}`, options: { breakLine: false } });
  });
  slide.addText(runs, {
    x, y, w, h, fontSize: opts.fontSize || 12.5, color: opts.color || C.ink,
    margin: opts.margin ?? 0.1, valign: 'top', fit: 'shrink', paraSpaceAfterPt: 5,
    fill: opts.fill ? { color: opts.fill } : undefined,
    line: opts.line ? { color: opts.line, width: 1 } : undefined,
  });
}

function code(slide, snippet, lang, x, y, w, h, fontSize=8.0) {
  const runs = codeToRuns(snippet.trim(), lang).map((r) => ({ text: r.text, options: { ...r.options, fontFace: 'Consolas', fontSize } }));
  slide.addText(runs, { x, y, w, h, margin: 0.08, fit: 'shrink', valign: 'top', fill: { color: C.codeBg }, line: { color: '334155', width: 1 } });
}

function label(slide, value, x, y, w, color=C.blue) {
  slide.addText(value, { x, y, w, h: 0.24, fontSize: 9, bold: true, color, margin: 0 });
}

function sideFile(slide, value, x, y, w=5.8) {
  slide.addText(`SIDE FILE: ${value}`, { x, y, w, h: 0.24, fontFace: 'Consolas', fontSize: 8.2, color: C.purple, margin: 0 });
}

function resultCard(slide, heading, body, x, y, w, h, color=C.green) {
  box(slide, x, y, w, h, 'FFFFFF', color);
  text(slide, heading, x+0.12, y+0.09, w-0.24, 0.28, { fontSize: 11.5, bold: true, color });
  text(slide, body, x+0.12, y+0.39, w-0.24, h-0.5, { fontSize: 10.5, color: C.ink });
}

function addStepHeader(slide, n, labelText, subtitle, color) {
  title(slide, `Step ${n}: ${labelText}`, subtitle);
  stepBadge(slide, n, labelText, color);
}

let sn = 0;
function addSlideNumber(slide, note='') { sn += 1; footer(slide, sn, note); }

// 1 cover
{
  const s = pptx.addSlide();
  s.background = { color: C.navy };
  s.addImage({ path: ASSET('flood_rescue_cover_16x9.png'), x: 0, y: 0, w: W, h: H });
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: H, fill: { color: '07101F', transparency: 44 }, line: { color: '07101F', transparency: 100 } });
  s.addText('Closing the Loop', { x: 0.62, y: 0.54, w: 7.1, h: 0.58, fontSize: 34, bold: true, color: C.white, margin: 0 });
  s.addText('Flood-SAR Implementation in Eight Verified Steps', { x: 0.64, y: 1.12, w: 9.8, h: 0.5, fontSize: 22, bold: true, color: 'D7E8FF', margin: 0 });
  s.addText('Emergency call → mission state → plans → predictions → TRACE → verification → revision → rescue', { x: 0.64, y: 1.78, w: 11.0, h: 0.34, fontSize: 13, color: C.white, margin: 0 });
  s.addText('Faithfulness rule: every slide points to code that exists; every limitation is labeled.', { x: 0.64, y: 6.73, w: 9.5, h: 0.32, fontSize: 13, bold: true, color: C.white, margin: 0.04, fill: { color: C.navy, transparency: 15 } });
  addSlideNumber(s, 'Replacement for the placeholder-heavy walkthrough');
}

// 2 meaning of 8
{
  const s = pptx.addSlide();
  title(s, 'What “eight steps” means', 'These are the eight operational responsibilities from call intake to a recorded rescue outcome.');
  const steps = [
    ['1','Ground call',C.blue], ['2','Build mission state',C.teal], ['3','Propose plans',C.purple], ['4','Predict + claim',C.orange],
    ['5','TRACE gate',C.red], ['6','Verify',C.cyan], ['7','Revise + replan',C.green], ['8','Rescue + persist',C.blue],
  ];
  steps.forEach((r,i)=>{
    const row = i<4?0:1; const col=i%4; const x=0.65+col*3.12; const y=1.65+row*2.12;
    box(s,x,y,2.7,1.42,'FFFFFF',r[2]);
    s.addText(r[0],{x:x+0.12,y:y+0.14,w:0.48,h:0.48,fontSize:20,bold:true,color:C.white,align:'center',valign:'mid',margin:0,fill:{color:r[2]},line:{color:r[2]},radius:0.24});
    text(s,r[1],x+0.72,y+0.16,1.82,0.42,{fontSize:13,bold:true,color:r[2]});
    text(s,[
      'EmergencyCall object','Controller-visible observation','PlanCandidate list','PlanPrediction + Claim',
      'TraceRecord + decision','Drone outcome','Revision + candidate repair','Commitment + outcome'
    ][i],x+0.14,y+0.72,2.42,0.46,{fontSize:10.2,color:C.muted});
  });
  text(s,'Do not confuse these with TRACE’s eight general writer stages. The crosswalk later shows which writer operations this domain-specific implementation actually realizes.',0.72,6.14,11.9,0.55,{fontSize:12,bold:true,fill:C.yellow,line:'F59E0B'});
  addSlideNumber(s,'Eight operational steps; eight writer stages are a separate taxonomy');
}

// 3 cast
{
  const s = pptx.addSlide();
  title(s,'One controller, two machines, one human, one world','The architecture is intentionally simple in the first implementation.');
  s.addImage({ path: ASSET('operational_cast.png'), ...imageSizingContain(ASSET('operational_cast.png'),0.5,1.38,7.0,5.45) });
  bullets(s,[
    'Flood Environment owns hidden truth and produces observations/outcomes.',
    'Survey drone observes; rescue boat executes. Neither plans.',
    'Mission Controller is one Python process containing planner, predictor, TRACE gate, and dispatcher.',
    'Incident Commander is an external authority boundary.',
    'Offline evaluation scores logs after the episode and sends no commands.'
  ],7.75,1.55,5.0,4.55,{fontSize:13.2,fill:'FFFFFF',line:C.line});
  text(s,'Current honesty note: IncidentCommander.authorizes() is a deterministic teaching stub, not a real human approval interface.',7.75,6.22,5.0,0.48,{fontSize:11.5,bold:true,fill:C.orangeLight,line:C.orange});
  addSlideNumber(s,'Source: src/trace_jepa/controller.py');
}

// 4 knowledge boundary
{
  const s = pptx.addSlide();
  title(s,'The knowledge boundary makes the episode scientifically valid','The controller knows what has been reported, not everything the simulator contains.');
  label(s,'MISSION CONTROLLER KNOWLEDGE',0.62,1.38,5.8,C.blue);
  s.addImage({ path: ASSET('mission_controller_knowledge.png'), ...imageSizingContain(ASSET('mission_controller_knowledge.png'),0.55,1.66,5.9,4.65) });
  label(s,'SIMULATION GROUND TRUTH',6.88,1.38,5.8,C.red);
  s.addImage({ path: ASSET('simulation_ground_truth.png'), ...imageSizingContain(ASSET('simulation_ground_truth.png'),6.82,1.66,5.9,4.65) });
  text(s,'North Channel = unknown',1.15,6.18,4.7,0.38,{fontSize:14,bold:true,color:C.blue,align:'center'});
  text(s,'North Channel = blocked',7.45,6.18,4.7,0.38,{fontSize:14,bold:true,color:C.red,align:'center'});
  addSlideNumber(s,'Hidden truth never enters planner/predictor/gate inputs');
}

// 5 how to run
{
  const s = pptx.addSlide();
  title(s,'Run the implementation from a raw emergency call','One command produces the timeline, records, evidence, commitments, summary, and figures.');
  code(s,`source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
cd /path/to/trace_jepa_flood_sar_starter
python -m pip install -e ".[dev]"
pytest

trace-jepa-call \\
  --call-file examples/calls/riverside_call.txt \\
  --output artifacts/runs/call_001`, 'bash',0.65,1.55,7.1,3.3,10.2);
  resultCard(s,'Input','Emergency. Four residents are stranded at Riverside Apartments. Flood water is rising and the road is inaccessible.',8.05,1.55,4.65,1.35,C.blue);
  resultCard(s,'Main outputs','emergency_call.json\ntimeline.txt\nsummary.json\nrecords/trace.jsonl\nevidence/*.json\ncommitments/*.jsonl\nfigures/*.svg',8.05,3.08,4.65,2.62,C.green);
  sideFile(s,'RUN_EIGHT_STEPS.md',0.67,5.17,6.8);
  text(s,'Expected core test state: all core tests pass; the optional PyTorch/V-JEPA test may be skipped until the ML stack is installed.',0.67,5.55,7.05,0.72,{fontSize:11.5,fill:C.yellow,line:'F59E0B'});
  addSlideNumber(s,'Entry point: trace_jepa.emergency_cli:main');
}

// 6 step1 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,1,'Accept and ground the emergency call','Convert raw caller language into an auditable EmergencyCall object without inventing missing fields.',C.blue);
  resultCard(s,'Input','raw_text\noptional --location\noptional --people\noptional deadline override',0.65,1.88,3.15,1.65,C.blue);
  resultCard(s,'Processing','closed location alias registry\nregex/number-word people count\nscenario default deadline\nexplicit validation errors',4.03,1.88,4.05,1.65,C.teal);
  resultCard(s,'Output','EmergencyCall\nnormalized_location_id\npeople_count\ndeadline_s\nraw call preserved',8.32,1.88,4.35,1.65,C.green);
  bullets(s,[
    'Ambiguous location → stop and request --location.',
    'Missing people count → stop and request --people.',
    'No geocoder is implemented yet.',
    'The call does not reveal route status.'
  ],0.65,4.0,5.5,1.75,{fontSize:12.5,fill:'FFFFFF',line:C.line});
  code(s,`Emergency. Four residents are stranded at Riverside Apartments.
Flood water is rising and the road is inaccessible.`, 'text',6.5,4.0,6.16,1.22,12);
  sideFile(s,'step01_call_intake/S01_intake.py',6.52,5.46,5.9);
  sideFile(s,'step01_call_intake/S01_emergency_cli.py',6.52,5.74,5.9);
  addSlideNumber(s,'Output artifact: emergency_call.json');
}

// 7 step1 code
{
  const s = pptx.addSlide();
  addStepHeader(s,1,'Code: parse the call','The slide shows the core logic; the complete source is in the labeled side file.',C.blue);
  const snippet = readLines(SRC('src/trace_jepa/intake.py'),125,164);
  code(s,snippet,'python',0.62,1.82,7.2,4.95,8.0);
  bullets(s,[
    'Location is normalized against scenario aliases.',
    'People count is parsed independently.',
    'Deadline is explicit and validated.',
    'EmergencyCall is frozen by the Pydantic contract.'
  ],8.12,1.83,4.55,2.08,{fontSize:12.2,fill:'FFFFFF',line:C.line});
  resultCard(s,'Exit test','normalized_location_id = riverside_apartments\npeople_count = 4\ndeadline_s = 1200',8.12,4.16,4.55,1.42,C.green);
  text(s,'Faithfulness boundary: this is deterministic text parsing, not speech recognition, NLP extraction, or geocoding.',8.12,5.83,4.55,0.68,{fontSize:11.2,bold:true,fill:C.orangeLight,line:C.orange});
  sideFile(s,'step01_call_intake/S01_intake.py',8.14,6.66,4.45);
  addSlideNumber(s,'Authoritative source: src/trace_jepa/intake.py');
}

// 8 step2 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,2,'Register the incident and build mission state','Create the controller-visible state while preserving hidden simulator truth.',C.teal);
  const obs = `Mission Controller sees:
- destination: riverside_apartments
- people: 4
- deadline: 1200 s
- north_channel: unknown
- south_detour: open
- drone battery: 0.82
- boat capacity: 6`;
  const truth = `Simulator holds:
- north_channel: blocked
- south_detour: open
- stranded_people: 4
- rescued: false`;
  code(s,obs,'text',0.65,1.82,5.75,3.15,12);
  code(s,truth,'text',6.94,1.82,5.75,2.15,12);
  text(s,'Only observe() enters MissionController._assess_observation(). simulation_ground_truth() is retained for tests and post-episode analysis.',6.94,4.24,5.75,0.92,{fontSize:12,bold:true,fill:C.yellow,line:'F59E0B'});
  sideFile(s,'step02_mission_state/S02_flood_environment.py',0.67,5.36,5.9);
  sideFile(s,'step02_mission_state/S02_riverside_flood_v1.yaml',0.67,5.67,5.9);
  sideFile(s,'step02_mission_state/S02_visualize.py',6.95,5.36,5.5);
  sideFile(s,'step02_mission_state/S02_fusion_state.py',6.95,5.67,5.5);
  resultCard(s,'Exit test','Controller north report = unknown\nTruth north status = blocked',6.94,6.0,5.75,0.72,C.green);
  addSlideNumber(s,'Source: FloodEnvironment.register_emergency_call / observe');
}

// 9 step2 code
{
  const s = pptx.addSlide();
  addStepHeader(s,2,'Code: the information boundary','The key correctness property is that observe() masks the blocked route until verification.',C.teal);
  const snippet = readLines(SRC('src/trace_jepa/scenario/flood_env.py'),38,83);
  code(s,snippet,'python',0.62,1.82,7.45,4.9,7.6);
  bullets(s,[
    'register_emergency_call changes mission parameters only.',
    'north_route_verified controls whether truth is exposed.',
    'initial_report is returned while unverified.',
    'simulation_ground_truth is a separate method.'
  ],8.35,1.85,4.33,2.18,{fontSize:12.1,fill:'FFFFFF',line:C.line});
  text(s,'The two SVG maps differ by one hidden fact. This is not cosmetic; it prevents ground-truth leakage.',8.35,4.36,4.33,0.84,{fontSize:11.6,bold:true,fill:C.greenLight,line:C.green});
  sideFile(s,'step02_mission_state/S02_flood_environment.py',8.36,5.55,4.2);
  addSlideNumber(s,'Test: tests/test_entity_model.py and test_emergency_call.py');
}

// 10 step3 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,3,'Generate grounded candidate actions','The planner says what is structurally possible; it does not predict or authorize.',C.purple);
  const cards = [
    ['North dispatch','rescue_boat_1\nrescue_base → riverside_apartments\nroute=north_channel\nirreversible\nauthority required',C.red],
    ['Drone verification','survey_drone_1\ndrone_pad → north_channel\npurpose=resolve_route_access\nreversible\nno dispatch authority',C.cyan],
    ['South dispatch','rescue_boat_1\nrescue_base → riverside_apartments\nroute=south_detour\nirreversible\nauthority required',C.green],
  ];
  cards.forEach((r,i)=>resultCard(s,r[0],r[1],0.68+i*4.2,1.85,3.85,2.22,r[2]));
  text(s,'Every PlanCandidate contains an ActionInstance with actor, origin, destination, route, people count, deadline, reversibility, utility, and authority requirement.',0.7,4.47,12.0,0.62,{fontSize:12.4,bold:true,fill:C.purpleLight,line:C.purple});
  sideFile(s,'step03_planning/S03_planner.py',0.72,5.44,5.6);
  sideFile(s,'step03_planning/S03_contracts_models.py',0.72,5.74,5.6);
  sideFile(s,'step03_planning/S03_flood_actions_v1.yaml',6.65,5.44,5.6);
  resultCard(s,'Exit test','Three initial candidates; no opaque action strings.',6.65,5.86,5.96,0.72,C.green);
  addSlideNumber(s,'Planner version: flood-planner-v2');
}

// 11 step3 code
{
  const s = pptx.addSlide();
  addStepHeader(s,3,'Code: propose actions from observed route reports','The planner generates boat dispatches for non-blocked reports and verification actions for unknown reports.',C.purple);
  const snippet = readLines(SRC('src/trace_jepa/planning/planner.py'),15,79);
  code(s,snippet,'python',0.58,1.82,8.1,4.95,7.2);
  bullets(s,[
    'No prediction values appear in this file.',
    'Unknown is not treated as open.',
    'A blocked route is omitted on replanning.',
    'choose() ranks only CLEAR/QUALIFY candidates.'
  ],8.96,1.84,3.72,2.15,{fontSize:11.8,fill:'FFFFFF',line:C.line});
  text(s,'Current limitation: this is a small deterministic candidate generator, not an HTN/MRTA solver.',8.96,4.3,3.72,0.74,{fontSize:11.3,bold:true,fill:C.orangeLight,line:C.orange});
  sideFile(s,'step03_planning/S03_planner.py',8.98,5.38,3.55);
  addSlideNumber(s,'Authoritative source: src/trace_jepa/planning/planner.py');
}

// 12 step4 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,4,'Predict consequences and formulate claims','The current predictor is a transparent deterministic fixture, not JEPA and not an empirical result.',C.orange);
  const rows = [
    ['North unknown','0.92','0.28','0.82','0.08','HOLD later'],
    ['Verify north','0.98','0.97','0.04','0.04','CLEAR later'],
    ['South open','0.82','0.93','0.08','0.14','CLEAR later'],
  ];
  const x=[0.72,3.52,5.05,6.55,8.05,9.55];
  ['Candidate','Success','Support','OOD','Uncertainty','Expected gate'].forEach((h,i)=>text(s,h,x[i],1.85,[2.65,1.38,1.38,1.38,1.38,2.25][i],0.35,{fontSize:10.8,bold:true,color:C.white,align:'center',fill:C.navy}));
  rows.forEach((r,ri)=>r.forEach((v,i)=>text(s,v,x[i],2.25+ri*0.72,[2.65,1.38,1.38,1.38,1.38,2.25][i],0.5,{fontSize:11,align:i===0?'left':'center',fill:ri%2?'F8FAFC':'FFFFFF',line:C.line})));
  text(s,'Claim generated for a boat plan: “north_channel is traversable and rescue_boat_1 can reach riverside_apartments before the deadline.”',0.72,4.65,11.95,0.66,{fontSize:12.3,bold:true,fill:C.orangeLight,line:C.orange});
  sideFile(s,'step04_prediction_claims/S04_toy_predictor.py',0.74,5.67,5.8);
  sideFile(s,'step04_prediction_claims/S04_claim_probe.py',6.62,5.67,5.8);
  resultCard(s,'Exit test','Success, support, OOD, uncertainty, horizon, and assumptions remain separate fields.',0.74,6.0,11.88,0.64,C.green);
  addSlideNumber(s,'Predictor version: toy-action-prefix-v2');
}

// 13 step4 code
{
  const s = pptx.addSlide();
  addStepHeader(s,4,'Code: the deliberate out-of-support teaching case','The predictor may report high success while also declaring low support and high OOD.',C.orange);
  const snippet1 = readLines(SRC('src/trace_jepa/predictor/toy.py'),39,56);
  const snippet2 = readLines(SRC('src/trace_jepa/claims/probes.py'),22,49);
  label(s,'PREDICTOR FIXTURE',0.62,1.78,5.9,C.orange);
  code(s,snippet1,'python',0.62,2.05,6.05,3.02,8.2);
  label(s,'TYPED CLAIM PROBE',6.94,1.78,5.7,C.purple);
  code(s,snippet2,'python',6.94,2.05,5.77,3.02,8.0);
  text(s,'The code explicitly labels claim confidence as a teaching proxy copied from plan success probability. It is not presented as a separately calibrated claim probability.',0.62,5.38,12.08,0.72,{fontSize:12,bold:true,fill:C.yellow,line:'F59E0B'});
  sideFile(s,'step04_prediction_claims/S04_toy_predictor.py',0.64,6.37,5.8);
  sideFile(s,'step04_prediction_claims/S04_claim_probe.py',6.95,6.37,5.6);
  addSlideNumber(s,'Faithful limitation: no learned world model is used yet');
}

// 14 step5 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,5,'Write TRACE records and apply the policy gate','Evidence is stored first; then a deterministic policy writes verdict, failed gates, missing evidence, repair, and consumer action.',C.red);
  const flow = [
    ['Claim','predictive + grounded'],['Evidence','support/OOD/uncertainty'],['Policy','hard gates'],['TraceRecord','status + repair'],['Consumer','CLEAR/HOLD/...']
  ];
  flow.forEach((r,i)=>{
    const x=0.55+i*2.52;
    resultCard(s,r[0],r[1],x,1.95,2.05,1.08,[C.blue,C.orange,C.red,C.purple,C.green][i]);
    if(i<4) s.addShape(pptx.ShapeType.chevron,{x:x+2.08,y:2.27,w:0.35,h:0.42,fill:{color:C.slate},line:{color:C.slate}});
  });
  const decisions=[
    ['North dispatch','DEFER','HOLD','model_support, out_of_distribution',C.red],
    ['Drone verification','ACCEPT','CLEAR','none',C.cyan],
    ['South dispatch','ACCEPT','CLEAR','none',C.green],
  ];
  decisions.forEach((r,i)=>{
    const y=3.55+i*0.75;
    text(s,r[0],0.75,y,3.0,0.5,{fontSize:11.4,bold:true,fill:'FFFFFF',line:C.line});
    text(s,r[1],3.75,y,1.55,0.5,{fontSize:11.4,bold:true,color:r[4],align:'center',fill:'FFFFFF',line:C.line});
    text(s,r[2],5.3,y,1.55,0.5,{fontSize:11.4,bold:true,color:r[4],align:'center',fill:'FFFFFF',line:C.line});
    text(s,r[3],6.85,y,5.72,0.5,{fontSize:10.8,fill:'FFFFFF',line:C.line});
  });
  sideFile(s,'step05_trace_gate/S05_policy.py',0.77,6.1,3.45);
  sideFile(s,'step05_trace_gate/S05_runtime.py',4.38,6.1,3.45);
  sideFile(s,'step05_trace_gate/S05_storage.py',8.02,6.1,3.75);
  addSlideNumber(s,'Policy version: trace-flood-v1');
}

// 15 step5 code
{
  const s = pptx.addSlide();
  addStepHeader(s,5,'Code: hard gates cannot be averaged away','The 0.92 score is not read as permission when support and OOD checks fail.',C.red);
  const snippet = readLines(SRC('src/trace_jepa/runtime/policy.py'),61,119);
  code(s,snippet,'python',0.6,1.82,8.4,4.95,7.25);
  bullets(s,[
    'Failed technical gates + irreversible action → HOLD.',
    'Failed gates + reversible evidence probe → QUALIFY when enabled.',
    'Authority missing → ESCALATE.',
    'No failed gates → CLEAR.'
  ],9.28,1.85,3.42,2.35,{fontSize:11.7,fill:'FFFFFF',line:C.line});
  resultCard(s,'North result','status = defer\ndecision = hold\nmissing = supported/current route evidence\nrepair = send drone',9.28,4.47,3.42,1.4,C.red);
  sideFile(s,'step05_trace_gate/S05_policy.py',9.3,6.18,3.28);
  addSlideNumber(s,'Test: tests/test_policy.py');
}

// 16 writer crosswalk
{
  const s = pptx.addSlide();
  title(s,'How this domain writer maps to TRACE’s eight writer stages','Faithfulness requires stating what is implemented and what is not.');
  const rows=[
    ['0 Detect','Planner emits an explicit action-licensing claim candidate.','No open-ended argument detector.'],
    ['1 Intake','Probe + controller fill grounding, evidence, provenance, assumptions.','Implemented structurally.'],
    ['2 Type','ClaimLayer.PREDICTIVE.','Implemented.'],
    ['3 Question','Support, OOD, uncertainty, horizon, freshness, contradiction, authority.','Domain-specific question set.'],
    ['4 Test','PolicyEngine.evaluate runs deterministic checks.','Implemented.'],
    ['5 Elicit','Failed record names drone verification as missing evidence/repair.','No debate module.'],
    ['6 Settle','Policy maps tests to record status and consumer decision.','No attack graph.'],
    ['7 Complete','Runtime writes record, gates, missing, repair, provenance, consumer action.','Implemented.'],
  ];
  const y0=1.45;
  rows.forEach((r,i)=>{
    const y=y0+i*0.63;
    text(s,r[0],0.58,y,1.45,0.49,{fontSize:10.2,bold:true,color:C.white,align:'center',fill:[C.blue,C.teal,C.purple,C.orange,C.red,C.cyan,C.green,C.blue][i]});
    text(s,r[1],2.05,y,7.0,0.49,{fontSize:10.1,fill:i%2?'F8FAFC':'FFFFFF',line:C.line});
    text(s,r[2],9.08,y,3.65,0.49,{fontSize:10.1,bold:true,color:i===5||i===6?C.orange:C.muted,fill:i%2?'F8FAFC':'FFFFFF',line:C.line});
  });
  text(s,'Conclusion: the current flood code is a conforming structured writer for predictive plan claims. It is not yet the full general-purpose eight-stage natural-language writer.',0.62,6.58,12.05,0.45,{fontSize:12.1,bold:true,fill:C.yellow,line:'F59E0B'});
  addSlideNumber(s,'Do not claim debate or attack-graph implementation');
}

// 17 step6 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,6,'Select and execute the evidence-seeking action','The highest-utility admissible action is the drone verification, not the held north dispatch.',C.cyan);
  const flow=[
    ['Candidates','North HOLD\nVerify CLEAR\nSouth CLEAR',C.purple],
    ['choose()','Rank only CLEAR/QUALIFY\nVerify utility 0.90\nSouth utility 0.685',C.blue],
    ['commit()','Action + authorizing\nrecord ID/version',C.red],
    ['execute()','Drone battery 0.82→0.74\nroute_status=blocked',C.green],
  ];
  flow.forEach((r,i)=>{
    resultCard(s,r[0],r[1],0.65+i*3.12,2.0,2.72,1.75,r[2]);
    if(i<3) s.addShape(pptx.ShapeType.chevron,{x:3.45+i*3.12,y:2.66,w:0.22,h:0.34,fill:{color:C.slate},line:{color:C.slate}});
  });
  code(s,`[06] ACTION SELECTED    survey drone 1 verifies north channel
[07] ACTION DISPATCHED  authorized command sent to survey_drone_1
[08] OBSERVATION RECEIVED north_channel is blocked`, 'text',0.72,4.35,11.9,1.2,11.2);
  sideFile(s,'step06_verification_dispatch/S06_controller.py',0.73,5.88,5.7);
  sideFile(s,'step06_verification_dispatch/S06_flood_environment.py',6.54,5.88,5.8);
  resultCard(s,'Exit test','A route observation exists only after a committed verify_route action.',0.73,6.2,11.72,0.62,C.green);
  addSlideNumber(s,'Detailed events 06-08');
}

// 18 step6 code
{
  const s = pptx.addSlide();
  addStepHeader(s,6,'Code: commitment before execution','A durable action is written with the exact record version that authorized it.',C.cyan);
  const snippet1=readLines(SRC('src/trace_jepa/controller.py'),291,324);
  const snippet2=readLines(SRC('src/trace_jepa/runtime/runtime.py'),115,128);
  label(s,'MISSION CONTROLLER',0.62,1.78,6.1,C.cyan);
  code(s,snippet1,'python',0.62,2.05,7.15,3.82,7.8);
  label(s,'TRACE RUNTIME COMMIT',8.02,1.78,4.7,C.red);
  code(s,snippet2,'python',8.02,2.05,4.68,2.42,8.2);
  text(s,'The commitment object is the closure link: action ↔ authorizing_record_id/version ↔ consumer policy.',8.02,4.8,4.68,0.82,{fontSize:11.7,bold:true,fill:C.redLight,line:C.red});
  sideFile(s,'step06_verification_dispatch/S06_controller.py',0.64,6.25,5.8);
  sideFile(s,'step06_verification_dispatch/S06_runtime.py',8.03,6.25,4.55);
  addSlideNumber(s,'Commitment log enforces closure');
}

// 19 step7 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,7,'Revise append-only and locally replan','Reality contradicts the north prediction; the old record remains and a new version rejects it.',C.green);
  const cols=[
    ['Before','North record v2\nstatus=DEFER\nconsumer=HOLD\nrepair=verify route',C.orange],
    ['Observation','survey_drone_1\nroute_status=blocked\nsource and battery recorded',C.cyan],
    ['Revision','same record_id\nrecord_version=3\nstatus=REJECT\nfailed_gate=realized_contradiction',C.red],
    ['Replan','blocked north omitted\nSouth candidate remains\nverification preserved',C.green],
  ];
  cols.forEach((r,i)=>{
    resultCard(s,r[0],r[1],0.6+i*3.15,1.95,2.78,2.12,r[2]);
    if(i<3) s.addShape(pptx.ShapeType.chevron,{x:3.42+i*3.15,y:2.80,w:0.20,h:0.32,fill:{color:C.slate},line:{color:C.slate}});
  });
  text(s,'Locality in the current code is route-specific candidate filtering. A general HTN dependency graph and arbitrary branch invalidation are future work.',0.7,4.54,11.95,0.72,{fontSize:12,bold:true,fill:C.yellow,line:'F59E0B'});
  sideFile(s,'step07_revision_repair/S07_controller.py',0.72,5.62,5.6);
  sideFile(s,'step07_revision_repair/S07_runtime.py',6.45,5.62,5.6);
  resultCard(s,'Exit test','Old record readable; revision supersedes it; north dispatch absent after re-observation.',0.72,5.98,11.75,0.72,C.green);
  addSlideNumber(s,'Detailed events 09-11');
}

// 20 step7 code
{
  const s = pptx.addSlide();
  addStepHeader(s,7,'Code: append a contradiction instead of editing history','The revision adds outcome evidence, a new status, a failed gate, and a repair.',C.green);
  const snippet1=readLines(SRC('src/trace_jepa/runtime/runtime.py'),90,113);
  const snippet2=readLines(SRC('src/trace_jepa/controller.py'),332,395);
  label(s,'RUNTIME REVISION',0.62,1.78,5.5,C.green);
  code(s,snippet1,'python',0.62,2.04,5.6,3.6,7.9);
  label(s,'CONTROLLER CONTRADICTION + REPLAN',6.5,1.78,6.2,C.red);
  code(s,snippet2,'python',6.5,2.04,6.2,3.6,6.8);
  text(s,'No field in the prior committed record is changed in place.',0.64,5.92,5.55,0.45,{fontSize:12,bold:true,fill:C.greenLight,line:C.green});
  text(s,'The re-observed route report becomes blocked, so FloodPlanner.propose() no longer emits the north dispatch.',6.52,5.92,6.14,0.62,{fontSize:11.5,bold:true,fill:C.redLight,line:C.red});
  addSlideNumber(s,'Append-only record semantics');
}

// 21 step8 overview
{
  const s = pptx.addSlide();
  addStepHeader(s,8,'Clear the final dispatch and record the rescue outcome','The final boat action is linked to a new TRACE record and the policy version that cleared it.',C.blue);
  const steps=[
    ['Reassess','South support=0.93\nOOD=0.08\nCLEAR',C.green],
    ['Authority','IncidentCommander\npermits dispatch_rescue_boat',C.orange],
    ['Commit','action + record ID/version\nwritten to commitment log',C.red],
    ['Execute','boat uses south_detour\npeople_reached=4',C.blue],
    ['Persist','summary + timeline\nrecords + evidence + figures',C.purple],
  ];
  steps.forEach((r,i)=>{
    resultCard(s,r[0],r[1],0.4+i*2.56,1.95,2.28,1.68,r[2]);
    if(i<4) s.addShape(pptx.ShapeType.chevron,{x:2.73+i*2.56,y:2.59,w:0.18,h:0.30,fill:{color:C.slate},line:{color:C.slate}});
  });
  code(s,`[12] FINAL ACTION SELECTED   boat via South Detour
[13] FINAL ACTION DISPATCHED  Commander approval + TRACE clearance recorded
[14] RESCUE OUTCOME            success=True, people_reached=4`, 'text',0.65,4.25,12.0,1.22,11.2);
  text(s,'Faithfulness boundary: “Commander approval” is currently a deterministic role stub. It demonstrates the authority field and gate, not a human-in-the-loop interface.',0.65,5.75,12.0,0.66,{fontSize:11.7,bold:true,fill:C.orangeLight,line:C.orange});
  sideFile(s,'step08_final_rescue/S08_controller.py',0.67,6.58,3.45);
  sideFile(s,'step08_final_rescue/S08_flood_environment.py',4.30,6.58,3.70);
  sideFile(s,'step08_final_rescue/S08_reporting.py',8.20,6.58,3.70);
  addSlideNumber(s,'Detailed events 12-14');
}

// 22 step8 code
{
  const s = pptx.addSlide();
  addStepHeader(s,8,'Code: final authority, commitment, execution, and summary','The final record closure can be reconstructed from summary.json and the append-only logs.',C.blue);
  const snippet=readLines(SRC('src/trace_jepa/controller.py'),411,477);
  code(s,snippet,'python',0.6,1.82,8.35,4.95,6.9);
  bullets(s,[
    'Select supported south plan.',
    'Create final commitment.',
    'Log record ID and version.',
    'Execute simulated boat action.',
    'Write final outcome and summary.',
    'Verify record hash chain.'
  ],9.25,1.84,3.45,2.9,{fontSize:11.8,fill:'FFFFFF',line:C.line});
  resultCard(s,'Exit test','rescued = true\npeople_reached = 4\nrecord_chain_valid = true',9.25,5.08,3.45,1.08,C.green);
  addSlideNumber(s,'Authoritative source: MissionController.run_episode');
}

// 23 14 events mapping
{
  const s = pptx.addSlide();
  title(s,'The detailed fourteen-event log maps cleanly to the eight steps','The CLI stays granular for audit; the deck groups events by architectural responsibility.');
  const map=[
    ['1','01 CALL RECEIVED'],['2','02 MISSION STATE'],['3','03-05 PLAN ASSESSED'],['4','03-05 prediction + claim inside assessment'],
    ['5','03-05 TRACE status and decision'],['6','06-08 select / dispatch / observe'],['7','09-11 revise / replan / reassess'],['8','12-14 select / dispatch / outcome']
  ];
  map.forEach((r,i)=>{
    const y=1.45+i*0.63;
    text(s,`STEP ${r[0]}`,0.62,y,1.2,0.45,{fontSize:10.3,bold:true,color:C.white,align:'center',fill:[C.blue,C.teal,C.purple,C.orange,C.red,C.cyan,C.green,C.blue][i]});
    text(s,r[1],1.86,y,5.4,0.45,{fontSize:10.7,bold:true,fill:i%2?'F8FAFC':'FFFFFF',line:C.line});
    text(s,[
      'intake.py / emergency_cli.py','flood_env.py','planner.py','toy.py / probes.py','policy.py / runtime.py','controller.py / flood_env.py','runtime.py / controller.py / planner.py','controller.py / reporting.py'
    ][i],7.3,y,5.38,0.45,{fontFace:'Consolas',fontSize:9.5,fill:i%2?'F8FAFC':'FFFFFF',line:C.line});
  });
  text(s,'The event log is an operational trace, not the TRACE record itself. TRACE records are stored separately under records/trace.jsonl.',0.65,6.63,12.0,0.38,{fontSize:11.7,bold:true,fill:C.yellow,line:'F59E0B'});
  addSlideNumber(s,'Audit granularity: event timeline + reasoning records');
}

// 24 transcript
{
  const s = pptx.addSlide();
  title(s,'The episode as it actually runs','This output was reproduced from the packaged code with PYTHONPATH=src.');
  const timeline=fs.readFileSync(SRC('artifacts/runs/emergency_call_example/timeline.txt'),'utf8');
  code(s,timeline,'text',0.58,1.42,12.15,5.42,8.8);
  sideFile(s,'sample_run/timeline.txt',0.63,6.88,5.4);
  addSlideNumber(s,'No “forthcoming” placeholder on this slide');
}

// 25 artifacts
{
  const s = pptx.addSlide();
  title(s,'What one run leaves behind','Every important transition has a durable artifact.');
  code(s,`artifacts/runs/call_001/
├── emergency_call.json
├── timeline.txt
├── summary.json
├── records/trace.jsonl
├── evidence/*.json
├── commitments/commitments.jsonl
└── figures/
    ├── operational_cast.svg
    ├── mission_controller_knowledge.svg
    ├── simulation_ground_truth.svg
    └── action_timeline.svg`, 'text',0.65,1.55,6.0,4.75,11.2);
  const cards=[
    ['Call','Original report + normalized location/count/deadline',C.blue],
    ['Evidence','Versioned model outputs, hashes, assumptions, support',C.orange],
    ['Records','Status, gates, missing items, repair, consumer action',C.red],
    ['Commitments','Exact action + authorizing record ID/version',C.purple],
    ['Outcomes','What the simulator revealed after execution',C.green],
  ];
  cards.forEach((r,i)=>resultCard(s,r[0],r[1],7.0,1.55+i*1.03,5.6,0.82,r[2]));
  addSlideNumber(s,'Closure can be checked from stored files alone');
}

// 26 implemented vs not
{
  const s = pptx.addSlide();
  title(s,'What is implemented, what is a fixture, and what remains future work','A faithful tutorial must not let a clean demo masquerade as a completed research system.');
  const rows=[
    ['Emergency-call parser','Implemented','Closed alias registry + deterministic count extraction'],
    ['Flood environment','Implemented teaching simulator','Static scenario; no dynamic hydrology'],
    ['Planner','Implemented teaching planner','Three candidate patterns; no HTN/MRTA solver'],
    ['Predictor','Deterministic fixture','No JEPA or learned flood dynamics yet'],
    ['Claim bridge','Implemented','Predictive claims only in this demo'],
    ['TRACE policy/runtime','Implemented','Domain-specific gates; no full debate/attack graph'],
    ['Authority','Teaching stub','No live human approval interface'],
    ['Dispatcher','Simulated','No physical drone/boat integration'],
    ['Local repair','Implemented narrowly','Route-specific filtering, not general dependency repair'],
  ];
  ['Component','Current status','Boundary'].forEach((h,i)=>text(s,h,[0.55,3.45,5.9][i],1.38,[2.9,2.45,6.85][i],0.38,{fontSize:10.7,bold:true,color:C.white,align:'center',fill:C.navy}));
  rows.forEach((r,ri)=>r.forEach((v,i)=>text(s,v,[0.55,3.45,5.9][i],1.8+ri*0.54,[2.9,2.45,6.85][i],0.43,{fontSize:9.7,bold:i===1,color:i===1?(r[1].includes('Implemented')?C.green:C.orange):C.ink,fill:ri%2?'F8FAFC':'FFFFFF',line:C.line})));
  text(s,'This is an executable architectural demonstration. It is not yet the AAAI evaluation, a real rescue system, or evidence that JEPA improves flood response.',0.62,6.78,12.05,0.32,{fontSize:11.4,bold:true,fill:C.redLight,line:C.red});
  addSlideNumber(s,'Honest boundary conditions');
}

// 27 tests
{
  const s = pptx.addSlide();
  title(s,'Verification matrix','Each step has an observable exit condition and at least one relevant test or artifact.');
  const rows=[
    ['1 Call','test_emergency_call.py','Call grounds location/count; ambiguity fails explicitly'],
    ['2 State','test_entity_model.py','Controller view excludes hidden route truth'],
    ['3 Plans','test_end_to_end.py','Grounded actions and candidate set'],
    ['4 Prediction','test_end_to_end.py','Separate success/support/OOD/uncertainty'],
    ['5 Gate','test_policy.py','Unsupported high-confidence dispatch is held'],
    ['6 Verify','test_end_to_end.py','Verification has commitment and returns route observation'],
    ['7 Revise','test_end_to_end.py','Old record preserved; revision and south repair'],
    ['8 Rescue','test_closure.py + end-to-end','Final commitment cites record; chain valid; four reached'],
  ];
  ['Step','Test / artifact','Pass condition'].forEach((h,i)=>text(s,h,[0.55,2.4,5.1][i],1.42,[1.85,2.7,7.65][i],0.4,{fontSize:10.8,bold:true,color:C.white,align:'center',fill:C.navy}));
  rows.forEach((r,ri)=>r.forEach((v,i)=>text(s,v,[0.55,2.4,5.1][i],1.86+ri*0.59,[1.85,2.7,7.65][i],0.48,{fontSize:9.7,bold:i===0,fill:ri%2?'F8FAFC':'FFFFFF',line:C.line})));
  code(s,'pytest', 'bash',0.62,6.66,2.0,0.35,11);
  text(s,'Expected: core suite passes; optional PyTorch/V-JEPA adapter test may skip before ML installation.',2.85,6.64,9.65,0.38,{fontSize:11.2,bold:true,fill:C.yellow,line:'F59E0B'});
  addSlideNumber(s,'Run tests before modifying the predictor');
}

// 28 code pack
{
  const s = pptx.addSlide();
  title(s,'Code pack and file labels','Long source files are supplied exactly, grouped by the step that uses them.');
  const tree=`docs/eight_step_deck/
├── side_files/
│   ├── CODE_MAP.md
│   ├── RUN_EIGHT_STEPS.md
│   ├── step01_call_intake/
│   ├── step02_mission_state/
│   ├── step03_planning/
│   ├── step04_prediction_claims/
│   ├── step05_trace_gate/
│   ├── step06_verification_dispatch/
│   ├── step07_revision_repair/
│   ├── step08_final_rescue/
│   ├── complete_source/
│   └── sample_run/
├── build_eight_step_deck.js
├── TRACE_JEPA_Flood_SAR_8_Steps.pptx
└── TRACE_JEPA_Flood_SAR_8_Steps.pdf`;
  code(s,tree,'text',0.65,1.55,6.25,4.95,10.2);
  bullets(s,[
    'Every S01-S08 file is an exact source copy.',
    'CODE_MAP.md maps step → authoritative path → functions.',
    'The deck shows short excerpts only.',
    'complete_source/ mirrors package, configs, and tests.',
    'sample_run/ contains the verified episode artifacts.'
  ],7.25,1.65,5.35,2.65,{fontSize:12.6,fill:'FFFFFF',line:C.line});
  resultCard(s,'Use in class','Students first read the step, run the command, inspect the artifact, then open the side file when the excerpt is insufficient.',7.25,4.68,5.35,1.42,C.purple);
  sideFile(s,'CODE_MAP.md',7.27,6.4,5.0);
  addSlideNumber(s,'No code is reachable only by hunting through slides');
}

// 29 next steps
{
  const s = pptx.addSlide();
  title(s,'What comes next after the eight-step baseline','Replace fixtures one seam at a time without moving the TRACE boundary.');
  const next=[
    ['A','Real geocoder','Replace closed aliases; retain EmergencyCall contract',C.blue],
    ['B','Real visual encoder','Replace MockVideoEncoder with V-JEPA 2.1 feature cache',C.purple],
    ['C','Learned dynamics','Replace ToyActionPrefixPredictor with flood-domain predictor',C.orange],
    ['D','Calibrated probes','Separate plan success from predicate probability',C.teal],
    ['E','General planner','HTN/MRTA + explicit dependency graph',C.green],
    ['F','Human interface','Signed Incident Commander approval workflow',C.red],
    ['G','Evaluation','Fixed scenarios; vary audit substrate; report safety/utility/latency',C.blue],
  ];
  next.forEach((r,i)=>{
    const y=1.48+i*0.73;
    text(s,r[0],0.62,y,0.48,0.48,{fontSize:13,bold:true,color:C.white,align:'center',fill:r[3]});
    text(s,r[1],1.18,y,2.6,0.48,{fontSize:11.5,bold:true,color:r[3],fill:'FFFFFF',line:C.line});
    text(s,r[2],3.78,y,8.9,0.48,{fontSize:11.2,fill:'FFFFFF',line:C.line});
  });
  text(s,'The baseline is valuable because every replacement can be checked against the same eight-step contract and durable artifacts.',0.65,6.77,12.0,0.3,{fontSize:11.7,bold:true,fill:C.greenLight,line:C.green});
  addSlideNumber(s,'Architectural continuity across model upgrades');
}

// 30 definition done
{
  const s = pptx.addSlide();
  title(s,'Definition of done','A reviewer can answer all eight questions from stored artifacts alone.');
  const qs=[
    '1. What did the caller report, and how was the location grounded?',
    '2. What did Mission Control know, and what remained hidden?',
    '3. Which candidate actions were structurally available?',
    '4. What did the predictor claim, with what support and uncertainty?',
    '5. Which TRACE gates passed or failed, and what repair was named?',
    '6. Which evidence-seeking action was authorized and executed?',
    '7. What observation forced revision, and which branch changed?',
    '8. Which record and policy authorized the final rescue, and what happened?'
  ];
  qs.forEach((q,i)=>{
    const col=i<4?0:1; const row=i%4; const x=0.65+col*6.2; const y=1.55+row*1.25;
    box(s,x,y,5.8,0.95,'FFFFFF',[C.blue,C.teal,C.purple,C.orange,C.red,C.cyan,C.green,C.blue][i]);
    text(s,q,x+0.16,y+0.16,5.48,0.58,{fontSize:11.5,bold:true,color:C.ink});
  });
  text(s,'Better models may replace the fixtures later. The accountability boundary and these reconstruction questions stay fixed.',0.68,6.75,11.95,0.3,{fontSize:11.8,bold:true,fill:C.yellow,line:'F59E0B'});
  addSlideNumber(s,'Eight verified steps, one reconstructable operational history');
}

for (const slide of pptx._slides) {
  warnIfSlideHasOverlaps(slide, pptx, { ignoreLines: true, ignoreDecorativeShapes: true, muteContainment: true });
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

pptx.writeFile({ fileName: path.join(__dirname, 'TRACE_JEPA_Flood_SAR_8_Steps.pptx') });
