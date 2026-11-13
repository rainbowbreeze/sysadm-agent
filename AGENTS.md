# AI-Sysadm (`sysadm-agent`) — Agent Rules & Architecture

`sysadm-agent` is an **AI-Agent-Native system administration platform** that uses **Ansible** and **Agent Skills** (`_agents/skills/ai-sysadm-*`) to install, configure, and maintain Linux machines across a network.

---

## 1. Core Operational & Security Invariants

1. **Documentation & History Sync**:
   - Keep `AGENTS.md` aligned with core project architecture and conventions.
   - **Keep `AGENTS.md` lean (no redundant catalogs)**: Only store architectural invariants, rules, and conventions here. Never add static lists/catalogs of modules (`ansible/roles/`), skills (`_agents/skills/`), machines (`machines/`), or full directory trees that can be discovered dynamically from the filesystem or agent runtime.
   - Record every user request to change or modify the project in [project-history.md](file:///Users/alfredomorresi/Documents/develop/sysadm-agent/project-history.md).
2. **Git & Version Control Discipline**:
   - **Never stage (`git add`) or commit (`git commit`) changes** unless explicitly instructed to do so by the user.
3. **Public Repository Security Invariants**:
   - **Never hardcode** IP addresses, passwords, tokens, or sensitive usernames in any committed file (`machines/`, `ansible/`, `scripts/`).
   - Reference all sensitive and host-specific values from environment variables using Ansible's fail-fast lookup:
     `lookup('env', '<VAR_NAME>', default=undef('Missing required env var <VAR_NAME>'))`
   - Store all per-machine SSH keys inside `ssh_keys/` (gitignored except `.gitkeep`).
   - Store all machine installation logs inside `machines/<machine_name>/logs/` (gitignored except `.gitkeep`).

---

## 2. Architecture Conventions

- **Composable Modules (`ansible/roles/`)**:
  - All modules must be strictly **idempotent** and support multi-distro Linux (`Debian`, `Alpine`, `RedHat`, `Archlinux`).
  - `ansible/roles/baseline` is **mandatory** and always runs first on every machine.
  - All other roles in `ansible/roles/` are optional, composable modules. Inspect `ansible/roles/` and each role's `defaults/main.yml` dynamically when configuring machines or modules.
- **Per-Machine Folders (`machines/<machine_name>/`)**:
  - Contains `inventory.yml`, `vars.yml`, `playbook.yml`, and `logs/` (gitignored).
- **SSH Keys (`ssh_keys/`)**:
  - Referenced per machine via `ansible_ssh_private_key_file: "{{ playbook_dir }}/../../ssh_keys/<key_name>"` in `inventory.yml` and `baseline_ssh_pub_key_file: "{{ playbook_dir }}/../../ssh_keys/<key_name>.pub"` in `vars.yml`.

---

## 3. Environment Variable Naming Rule

All environment variables MUST use **underscores (`_`) only** (never hyphens) and follow the pattern:

```text
<MACHINE_NAME>_<SERVICE>_<VALUE>
```
*(or `<MACHINE_NAME>_<VALUE>` for host-level properties, where `<MACHINE_NAME>` itself contains no underscores, e.g. `RPICamera06`)*

- **Examples**: `RPICamera06_IP`, `RPICamera06_SSH_PORT`, `RPICamera06_SSH_USER`, `RPICamera06_SSH_PASS`, `RPICamera06_BECOME_PASS`, `RPICamera06_CAMERA_USER`.
- **Required vs. Optional in YAML**:
  ```yaml
  ansible_host: "{{ lookup('env', 'RPICamera06_IP', default=undef('Missing required env var RPICamera06_IP')) }}"
  ansible_port: "{{ lookup('env', 'RPICamera06_SSH_PORT') | default('22', true) | int }}"
  ansible_ssh_pass: "{{ lookup('env', 'RPICamera06_SSH_PASS') | default(omit, true) }}"
  ```

---

## 4. Orchestration CLI Reference

```bash
# Initial local setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Validate required env vars and ssh_keys/ for a machine
python3 scripts/check-env.py <machine_name>

# Run Ansible configuration (saves logs to machines/<machine_name>/logs/)
./scripts/run-machine.sh <machine_name> [--check]
```
