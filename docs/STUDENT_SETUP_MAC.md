# TRACE-WorldModel Flood-SAR  
## Student Setup and Clone Guide for macOS

This guide prepares a MacBook for the TRACE-WorldModel D0.5 Flood-SAR workshop.

Complete the installation, clone, geography download, and first test run **before the scheduled code lab** whenever possible.

## What students will install

- TRACE-WorldModel source repository
- Python 3.12 environment
- D0.5 browser workbench
- Antioch Delta road and waterway geography
- Development and testing dependencies

## Repository information

```text
Repository: eyuchang/trace-worldmodel-flood-sar
Main branch: main
Workshop release: v0.5-workshop
Browser URL: http://127.0.0.1:8030/d05
```

The source code is stored in GitHub.

Two large generated geography files are distributed separately through the GitHub Release:

```text
roads.geojson
road_graph.json
```

---

# 1. Obtain access to the private repository

The repository is private during workshop preparation.

Before beginning:

1. Create or use a GitHub account.
2. Send your GitHub username to the instructor.
3. Accept the GitHub repository invitation.
4. Confirm that you can open the TRACE-WorldModel repository while signed in.

GitHub authentication is account-based. You authenticate GitHub CLI once on your Mac; you do not need a separate authentication code for each repository.

---

# 2. Open Terminal

Open:

```text
Applications → Utilities → Terminal
```

Check Git:

```bash
git --version
```

When macOS asks to install Command Line Tools, approve the installation.

When Git is not available, run:

```bash
xcode-select --install
```

---

# 3. Verify Homebrew

Run:

```bash
brew --version
```

When Homebrew is already installed, continue.

When `brew` is not found, install Homebrew according to the instructor’s Mac setup guide before continuing.

---

# 4. Install GitHub CLI

Check whether GitHub CLI is already installed:

```bash
gh --version
```

When it is missing:

```bash
brew install gh
```

Verify:

```bash
gh --version
```

---

# 5. Authenticate GitHub CLI

Run:

```bash
gh auth login
```

Choose:

```text
Where do you use GitHub?
GitHub.com

Preferred protocol for Git operations?
HTTPS

Authenticate Git with GitHub credentials?
Yes

Authentication method?
Login with a web browser
```

Terminal will display a one-time code.

1. Copy the code.
2. Complete authorization in the browser.
3. Return to Terminal.

Verify authentication:

```bash
gh auth status
```

The result should identify your GitHub account and show:

```text
Active account: true
Git operations protocol: https
```

Verify that your account can access the repository:

```bash
gh repo view eyuchang/trace-worldmodel-flood-sar
```

Do not continue until this command succeeds.

---

# 6. Clone the repository

Create a project directory:

```bash
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
```

Clone the repository:

```bash
gh repo clone eyuchang/trace-worldmodel-flood-sar
```

Enter the repository:

```bash
cd "$HOME/Projects/trace-worldmodel-flood-sar"
```

Verify:

```bash
git status
git branch --show-current
git remote -v
```

Expected branch:

```text
main
```

Expected status:

```text
nothing to commit, working tree clean
```

---

# 7. Create a student work branch

Do not modify the instructor’s `main` branch directly.

Create a local student branch:

```bash
git switch -c student-work
```

Verify:

```bash
git branch --show-current
```

Expected:

```text
student-work
```

Do not push changes to the instructor repository unless the instructor explicitly requests it.

---

# 8. Download the workshop geography package

Create a download directory:

```bash
mkdir -p "$HOME/Downloads/trace-jepa-assets"
```

Download the archive and checksum from the `v0.5-workshop` release:

```bash
gh release download v0.5-workshop \
  --repo eyuchang/trace-worldmodel-flood-sar \
  --pattern 'antioch_delta_real_v1.tar.gz*' \
  --dir "$HOME/Downloads/trace-jepa-assets"
```

List the downloaded files:

```bash
ls -lh "$HOME/Downloads/trace-jepa-assets"
```

Expected:

```text
antioch_delta_real_v1.tar.gz
antioch_delta_real_v1.tar.gz.sha256
```

---

# 9. Verify the geography archive

Enter the download directory:

```bash
cd "$HOME/Downloads/trace-jepa-assets"
```

Verify the checksum:

```bash
shasum -a 256 -c \
  antioch_delta_real_v1.tar.gz.sha256
```

Expected:

```text
antioch_delta_real_v1.tar.gz: OK
```

Do not use the archive when checksum verification fails.

Delete it and download it again instead.

---

# 10. Extract the geography data

Return to the repository:

```bash
cd "$HOME/Projects/trace-worldmodel-flood-sar"
```

Extract the archive:

```bash
tar -xzf \
  "$HOME/Downloads/trace-jepa-assets/antioch_delta_real_v1.tar.gz" \
  -C data/geography
```

Verify the two large files:

```bash
ls -lh \
  data/geography/antioch_delta_real_v1/roads.geojson \
  data/geography/antioch_delta_real_v1/road_graph.json
```

Both files must exist before running D0.5.

Also inspect the geography directory:

```bash
find data/geography/antioch_delta_real_v1 \
  -maxdepth 1 \
  -type f \
  -print | sort
```

---

# 11. Load Conda

Load Miniforge:

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
```

Check Conda:

```bash
conda --version
```

When the command fails, Miniforge is not installed at the expected location. Follow the instructor’s Mac setup procedure before continuing.

---

# 12. Create the Python environment

Check existing environments:

```bash
conda env list
```

When `trace-jepa` does not already exist:

```bash
conda create \
  -n trace-jepa \
  python=3.12 \
  -y
```

Activate it:

```bash
conda activate trace-jepa
```

Verify Python:

```bash
python --version
which python
```

Expected Python version:

```text
Python 3.12
```

---

# 13. Install TRACE-WorldModel

From the repository root:

```bash
cd "$HOME/Projects/trace-worldmodel-flood-sar"
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install TRACE-WorldModel and workshop dependencies:

```bash
python -m pip install -e ".[ui,dev]"
```

The editable installation allows students to modify source code and immediately test the changes.

---

# 14. Verify the installation

Run:

```bash
trace-jepa-verify
```

Then run the test suite:

```bash
python -m pytest -q
```

Required core tests should pass.

Some optional ML tests may be skipped when optional packages such as PyTorch are not installed.

Record the final test summary for the instructor.

---

# 15. Start the D0.5 browser workbench

From the repository root:

```bash
./scripts/run_d05.sh
```

Keep this Terminal window open.

The server stops when:

- the Terminal window is closed;
- the computer sleeps;
- `Control+C` is pressed.

Open a second Terminal window and run:

```bash
open "http://127.0.0.1:8030/d05"
```

The browser should display:

- the Bay Area Delta map;
- roads and waterways;
- reconnaissance drones;
- rescue boats;
- ambulances;
- incident controls;
- S1–S5 controls;
- TRACE records;
- mission activity;
- temporal schedules.

---

# 16. Complete the first acceptance test

Run one complete rescue before class.

1. Reset the simulation.
2. Select an incident location.
3. Enter incident severity.
4. Enter the number of stranded people.
5. Submit the 911 alert.
6. Observe drone reconnaissance.
7. Observe the selected boat or ground response.
8. Observe transfer-dock selection when applicable.
9. Observe ambulance dispatch and handoff.
10. Observe hospital delivery.
11. Confirm that the completed alert disappears from the active-alert list.
12. Inspect the TRACE panel.
13. Inspect the schedule panel.

A pickup alone does not count as rescue completion.

The rescue completes only when the people are safely delivered and accounted for.

---

# 17. Verify the mission invariant

During the rescue, verify that:

```text
people waiting
+ people onboard rescue assets
+ people at transfer locations
+ people in ambulances
+ people delivered
=
total people accounted for
```

No person should silently disappear from mission state.

---

# 18. Stop the server

Return to the Terminal running the server and press:

```text
Control + C
```

---

# 19. Pulling instructor updates

Before pulling updates, inspect your working tree:

```bash
cd "$HOME/Projects/trace-worldmodel-flood-sar"
git status
```

When `main` is clean:

```bash
git switch main
git pull --ff-only origin main
```

Return to the student branch:

```bash
git switch student-work
```

Do not merge instructor changes during the workshop unless instructed.

---

# 20. Troubleshooting

## Repository not found

Check authentication:

```bash
gh auth status
```

Check access:

```bash
gh repo view eyuchang/trace-worldmodel-flood-sar
```

Possible causes:

- invitation not accepted;
- wrong GitHub account;
- repository name typed incorrectly;
- authentication expired.

## Release not found

List available releases:

```bash
gh release list \
  --repo eyuchang/trace-worldmodel-flood-sar
```

Expected release:

```text
v0.5-workshop
```

## Checksum fails

Delete the downloaded files:

```bash
rm -f \
  "$HOME/Downloads/trace-jepa-assets/antioch_delta_real_v1.tar.gz" \
  "$HOME/Downloads/trace-jepa-assets/antioch_delta_real_v1.tar.gz.sha256"
```

Download them again using Section 8.

## Geography files missing

Repeat the extraction step:

```bash
cd "$HOME/Projects/trace-worldmodel-flood-sar"

tar -xzf \
  "$HOME/Downloads/trace-jepa-assets/antioch_delta_real_v1.tar.gz" \
  -C data/geography
```

## Conda command not found

Run:

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
```

## Browser page does not load

Confirm that the server is still running:

```bash
./scripts/run_d05.sh
```

Then open:

```text
http://127.0.0.1:8030/d05
```

## Browser shows an old version

Hard refresh Chrome:

```text
Command + Shift + R
```

## Fleet icons do not appear

Open the browser developer console and check for JavaScript errors.

The working marker implementation must retain:

```javascript
.addTo(map);
```

## Port 8030 already in use

Identify the process:

```bash
lsof -nP -iTCP:8030 -sTCP:LISTEN
```

Stop only the stale TRACE-WorldModel process, or ask the instructor for assistance.

---

# 21. Pre-lab completion checklist

Before Day 3, confirm:

- [ ] GitHub invitation accepted
- [ ] GitHub CLI installed
- [ ] GitHub CLI authenticated
- [ ] Repository cloned
- [ ] Student branch created
- [ ] Geography release downloaded
- [ ] Checksum verified
- [ ] Geography extracted
- [ ] Conda environment created
- [ ] TRACE-WorldModel installed
- [ ] Verification command passed
- [ ] Tests passed
- [ ] D0.5 browser opened
- [ ] One complete rescue executed
- [ ] TRACE records inspected

Bring a screenshot of the working D0.5 browser or the final test output to the workshop.
