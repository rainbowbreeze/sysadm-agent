---
name: ai-sysadm-provision-machine
description: >-
  Use this skill when the user asks AI-sysadm to install, configure, provision,
  or update a target machine using its configuration folder in `machines/<MACHINE_NAME>/`.
  Validates env vars and SSH keys, runs Ansible idempotently, and documents
  installation logs inside `machines/<MACHINE_NAME>/logs/`.
---

# AI-Sysadm: Provision Machine (`ai-sysadm-provision-machine`)

Follow these steps to execute a machine's configuration idempotently and document the installation logs in its folder.

> **Strict Isolation Rule**: During provisioning, **never modify** any committed files (`ansible/roles/`, `machines/<MACHINE_NAME>/*.yml`, or `scripts/`) or `.env`. Only write to `machines/<MACHINE_NAME>/logs/`.

## Step 1: Pre-Flight Validation (Fail & Stop on Missing Prerequisites)

1. **Verify Machine Folder & Ansible Binary**:
   - Check that `machines/<MACHINE_NAME>/inventory.yml`, `vars.yml`, and `playbook.yml` exist.
   - Check that `.venv/bin/ansible-playbook` (or system `ansible-playbook`) is installed.
   - If either the machine folder or Ansible is missing, **stop immediately** and ask the user to run the setup manually (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` or `ai-sysadm-configure-machine`). Do not auto-install `.venv` or scaffold files silently.
2. **Verify Required Environment Variables & SSH Keys**:
   ```bash
   python3 scripts/check-env.py <MACHINE_NAME>
   ```
   - If `check-env.py` exits with a non-zero code, **stop immediately** and ask the user to provide the missing `<MACHINE_NAME>_*` variables in `.env` or the missing SSH key pair in `ssh_keys/`.

## Step 2: Execute Ansible Configuration

> Note: In the sandboxed environment, SSH connections to LAN machines require network access (`BypassSandbox: true` on `run_command`).

1. **Default Execution (Full Playbook Apply)**:
   - By default, apply the configuration directly (only pass `--check` if the user explicitly requested a dry-run):
     ```bash
     ./scripts/run-machine.sh <MACHINE_NAME>
     ```
2. **Selective Module Execution (Optional `--tags`)**:
   - If the user asked to run or update only specific modules (e.g., `camera`), pass `--tags`:
     ```bash
     ./scripts/run-machine.sh <MACHINE_NAME> --tags <module_name>
     ```
3. **Dry-Run Mode (Only When Explicitly Requested)**:
   ```bash
   ./scripts/run-machine.sh <MACHINE_NAME> --check
   ```

## Step 3: Document Installation Logs & Handle Failures

1. **Raw Log Output**:
   - `scripts/run-machine.sh` automatically writes the full Ansible output to `machines/<MACHINE_NAME>/logs/ansible-<timestamp>.log` and updates the symlink `machines/<MACHINE_NAME>/logs/latest.log`.
2. **Append Run Summary to `machines/<MACHINE_NAME>/logs/history.md`**:
   - Read `machines/<MACHINE_NAME>/logs/latest.log` and append an entry (whether the run succeeded or failed) to `machines/<MACHINE_NAME>/logs/history.md` containing:
     - **Timestamp**: ISO-8601 date/time of execution
     - **Status**: `SUCCESS` / `FAILED` / `CHECK_MODE`
     - **Modules Applied**: List of roles executed (or `--tags` filter used)
     - **Ansible Recap**: `ok`, `changed`, `unreachable`, `failed`, `skipped` task counts
     - **Log File**: Filename of the raw log (`ansible-<timestamp>.log`)
     - **Notes**: Brief summary of changes applied or errors encountered (never include passwords or private keys).
3. **On Failure — Diagnose & Stop**:
   - If `scripts/run-machine.sh` exited with a non-zero status, after logging the failed run in `machines/<MACHINE_NAME>/logs/history.md`, analyze `machines/<MACHINE_NAME>/logs/latest.log` to identify the root cause, report the diagnosis clearly to the user, and **stop and ask for confirmation** before modifying any configuration or role files.
