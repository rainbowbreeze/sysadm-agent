# AI-Sysadm (`sysadm-agent`) — Agent Onboarding & Architecture Guide

`sysadm-agent` is an **AI-Agent-Native system administration platform** that uses **Ansible** and **Agent Skills** (`.agents/skills/ai-sysadm-*`) to install, configure, and maintain Linux machines across a network.

This file is the **entry point for any AI agent** working in this repository. Reading this document gives you full context on how the project is structured, how its components interact, which skill to load for each task, and the operational rules you must follow.

---

## 1. How the System Works (Mental Model)

1. **Composable Ansible Modules (`ansible/roles/`)**:
   - Every target machine first runs the mandatory **`baseline`** role (`ansible/roles/baseline/`), which configures the hostname, timezone, passwordless SSH key authorization, package updates and cache cleanup, observability tools, and hardens `sshd` on port **`21979`**.
   - Machines then combine any number of self-contained feature/hardware modules from `ansible/roles/<module_name>/` (e.g., `rainbowhat-imx7d`, `rainbowhat-raspberry`, `camera_<variant>`, `screen_<variant>`).
   - Target machines run **Debian/Ubuntu (`Debian`)** or **Alpine (`Alpine`)**.
   - Each role's `defaults/main.yml` contains a structured comment header documenting its purpose, supported OS families, default variables, and any required secret parameters in `machines/<MACHINE_NAME>/secrets.yml`, while `ansible/roles/<module_name>/README.md` documents the hardware mapping and how to control/use the module on the target machine. Agents discover modules dynamically by listing `ansible/roles/` and reading `defaults/main.yml` and `README.md`.

2. **Public Configs vs. Per-Machine Local Secrets**:
   - **Committed to GitHub**: Per-machine public Ansible files in `machines/<MACHINE_NAME>/` (`inventory.yml`, `vars.yml`, `playbook.yml`), roles in `ansible/roles/`, and runner scripts in `scripts/`.
   - **Kept Local Only (Gitignored)**:
     - `machines/<MACHINE_NAME>/secrets.yml`: Stores all per-machine private parameters and secrets (`machine_ip`, `machine_ssh_port`, `machine_ssh_user`, optional `machine_ssh_pass` / `machine_become_pass`, and any `<module_name>_*` secrets). Loaded by `playbook.yml` via `vars_files` and referenced in `inventory.yml` (`{{ machine_ip }}`, `{{ machine_ssh_user }}`).
     - `ssh_keys/`: Stores per-machine SSH private and public key pairs (`ssh_keys/<key_name>` and `ssh_keys/<key_name>.pub`) placed manually by the user for passwordless login.
     - `machines/<MACHINE_NAME>/logs/`: Stores raw timestamped Ansible logs (`ansible-<timestamp>.log`, `latest.log`) and the human-readable run log (`history.md`).

3. **Seamless SSH Bootstrap (`Port 22` -> `Port 21979` & Native `ssh_askpass`)**:
   - Fresh machines typically start with SSH on port `22`, while `baseline` moves `sshd` to port `21979` and disables password authentication after authorizing `ssh_keys/<key_name>.pub`.
   - `scripts/run-machine.sh` reads `machine_ip` and `machine_ssh_port` from `machines/<MACHINE_NAME>/secrets.yml`. `ansible-core >= 2.21` handles initial SSH password authentication natively via its built-in `ssh_askpass` mechanism without requiring `sshpass` or `paramiko`. If `machine_ssh_port` (`21979`) is not open yet and port `22` is reachable, `scripts/run-machine.sh` transparently passes `-e machine_ssh_port=22` for the initial bootstrap run. Once `baseline` updates `sshd`, it flushes handlers and switches the active connection to port `21979` mid-playbook.

---

## 2. Repository Layout

```text
sysadm-agent/
├── AGENTS.md                        # Entry-point guide & rules for AI agents (keep updated)
├── README.md                        # Human overview and skills table
├── ansible.cfg                      # Central Ansible configuration (roles_path = ./ansible/roles)
├── requirements.txt                 # Python dependencies (ansible-core, ansible-lint)
├── ssh_keys/                        # Per-machine SSH key pairs <key_name> & <key_name>.pub (GITIGNORED)
├── ansible/roles/
│   ├── baseline/                    # Mandatory base role (port 21979 sshd, packages, observability)
│   └── <module_name>/               # Self-contained composable modules (inspect dynamically)
├── machines/<MACHINE_NAME>/         # Per-machine configuration folders
│   ├── inventory.yml                # Host connection referencing secrets.yml vars & ssh_keys/<key_name>
│   ├── vars.yml                     # Public machine & module overrides + ssh_keys/<key_name>.pub
│   ├── secrets.yml                  # Per-machine private parameters & passwords (GITIGNORED)
│   ├── playbook.yml                 # Playbook loading vars.yml + secrets.yml & running tagged modules
│   └── logs/                        # Execution logs: ansible-*.log, latest.log, history.md (GITIGNORED)
├── scripts/
│   ├── check-env.py                 # Validates required secrets.yml parameters and ssh_keys/ files
│   └── run-machine.sh               # Runs check-env.py, handles port 22->21979 bootstrap, runs Ansible
└── .agents/skills/                  # Task-specific agent runbooks (always read before executing a task)
    ├── ai-sysadm-configure-machine/SKILL.md
    ├── ai-sysadm-provision-machine/SKILL.md
    └── ai-sysadm-create-module/SKILL.md
```

---

## 3. How to Interact with This Project (Agent Workflows)

Whenever the user asks you to perform one of the core workflows below, **read and follow the corresponding skill file first**:

1. **Define or Update a Machine (`machines/<MACHINE_NAME>/`)**
   - **Read**: [.agents/skills/ai-sysadm-configure-machine/SKILL.md](file:///Users/alfredomorresi/Documents/develop/sysadm-agent/.agents/skills/ai-sysadm-configure-machine/SKILL.md)
   - **What it does**: Interviews the user step-by-step (machine ID, derived hostname & SSH key pair in `ssh_keys/`, host IP `machine_ip` & SSH username `machine_ssh_user`, optional SSH/sudo passwords, `baseline` settings, and dynamic module selection from `ansible/roles/*/defaults/main.yml`), generates `machines/<MACHINE_NAME>/inventory.yml`, `vars.yml`, `playbook.yml`, and gitignored `secrets.yml`, and loops on `python3 scripts/check-env.py <MACHINE_NAME>` until all keys and parameters are ready.

2. **Install / Provision / Update a Target Machine**
   - **Read**: [.agents/skills/ai-sysadm-provision-machine/SKILL.md](file:///Users/alfredomorresi/Documents/develop/sysadm-agent/.agents/skills/ai-sysadm-provision-machine/SKILL.md)
   - **What it does**: Validates pre-flight requirements (`.venv`, `machines/<MACHINE_NAME>/`, `scripts/check-env.py`), runs `./scripts/run-machine.sh <MACHINE_NAME>` (or `--tags <module>` / `--check`), and logs the run summary in `machines/<MACHINE_NAME>/logs/history.md`.

3. **Create or Modify a Composable Module (`ansible/roles/<module_name>/`)**
   - **Read**: [.agents/skills/ai-sysadm-create-module/SKILL.md](file:///Users/alfredomorresi/Documents/develop/sysadm-agent/.agents/skills/ai-sysadm-create-module/SKILL.md)
   - **What it does**: Scaffolds a self-contained, idempotent role (`<category>_<variant>`) supporting `Debian` and/or `Alpine` with a structured header in `defaults/main.yml`, and presents all configured values to the user for confirmation or editing.

---

## 4. Per-Machine `secrets.yml` Variable Naming Rule

Because each machine has its own isolated, gitignored `machines/<MACHINE_NAME>/secrets.yml` file (loaded via `vars_files` in `playbook.yml`), private parameters use clean, lowercase `snake_case` YAML variable names without machine-name prefixes:

- **Host Connection Parameters**:
  - `machine_ip` *(required)*
  - `machine_ssh_port` *(optional, defaults to `21979`)*
  - `machine_ssh_user` *(required)*
  - `machine_ssh_pass` *(optional — included in `inventory.yml` & `secrets.yml` only when initial SSH password auth is needed)*
  - `machine_become_pass` *(optional — included in `inventory.yml` & `secrets.yml` only when `sudo` requires a password)*
- **Module-Specific Secrets**:
  - `<module_name>_<param>` (e.g., `camera_rtsp_password`)
- **Referenced in `machines/<MACHINE_NAME>/inventory.yml`**:
  ```yaml
  ansible_host: "{{ machine_ip }}"
  ansible_port: "{{ machine_ssh_port | default(21979, true) | int }}"
  ansible_user: "{{ machine_ssh_user }}"
  ```

---

## 5. Core Operational & Security Invariants

1. **Keep `AGENTS.md` Updated & Lean**:
   - Keep `AGENTS.md` updated with the latest architectural state of the project and how it works.
   - **No redundant catalogs**: Never add static lists of every module in `ansible/roles/` or every machine in `machines/`; discover them dynamically from the filesystem.
2. **Git & Version Control Discipline**:
   - **Never stage (`git add`) or commit (`git commit`) changes** unless explicitly instructed to do so by the user.
3. **Public Repository Security Invariants**:
   - **Never hardcode** IP addresses, passwords, tokens, or sensitive usernames in any committed file (`inventory.yml`, `vars.yml`, `playbook.yml`, `ansible/`, `scripts/`).
   - Store all per-machine private parameters inside gitignored `machines/<MACHINE_NAME>/secrets.yml`, all SSH keys inside `ssh_keys/`, and all execution logs inside `machines/<MACHINE_NAME>/logs/`.
4. **Strict Workflow Isolation**:
   - When configuring or provisioning a machine (`ai-sysadm-configure-machine` / `ai-sysadm-provision-machine`), **never modify** Ansible modules (`ansible/roles/`), `ansible.cfg`, or `scripts/`.
   - When creating or updating a module (`ai-sysadm-create-module`), **never modify** existing machine folders (`machines/<MACHINE_NAME>/`).

---

## 6. CLI Quick Reference

```bash
# Initial local setup on the orchestration machine
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Validate required parameters in machines/<MACHINE_NAME>/secrets.yml and key pairs in ssh_keys/
python3 scripts/check-env.py <MACHINE_NAME>

# Run Ansible configuration (auto-bootstraps port 22 -> 21979, logs to machines/<MACHINE_NAME>/logs/)
./scripts/run-machine.sh <MACHINE_NAME> [--tags <module>] [--check]
```
