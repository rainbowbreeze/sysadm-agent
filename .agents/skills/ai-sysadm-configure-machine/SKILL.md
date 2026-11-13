---
name: ai-sysadm-configure-machine
description: >-
  Use this skill when the user wants to define, create, or update the configuration
  for a machine in `machines/<MACHINE_NAME>/`. Interviews the user through a series
  of questions (modules to install, host connection details, SSH key in `ssh_keys/`,
  hostname, module settings), generates the Ansible files (`inventory.yml`, `vars.yml`,
  `playbook.yml`) plus the gitignored `machines/<MACHINE_NAME>/secrets.yml`, and verifies
  that all required parameters and SSH keys are ready.
---

# AI-Sysadm: Configure Machine (`ai-sysadm-configure-machine`)

Follow this interactive workflow to define or update a machine configuration under `machines/<MACHINE_NAME>/`. Ask questions step-by-step using `ask_question` (or conversational prompts when free-form text is needed).

## Step 1: Machine Identity & Derived Defaults

1. **Machine Identifier (`<MACHINE_NAME>`)**:
   - Ask for the machine identifier (e.g., `imx7panel`, `RPICamera06`, `LivingRoomScreen01`).
   - If `machines/<MACHINE_NAME>/` already exists, read its current `inventory.yml`, `vars.yml`, and `playbook.yml`, summarize its current configuration, and ask what the user wants to update.
2. **Confirm Derived Defaults**:
   - Derive the following defaults from `<MACHINE_NAME>` (where `<machine_name_lower>` is the lowercase form, e.g., `imx7panel`):
     - **Machine Config Folder**: `machines/<MACHINE_NAME>/`
     - **Target Hostname (`machine_hostname`)**: `<machine_name_lower>`
     - **SSH Key Pair in `ssh_keys/`**: `ssh_keys/<machine_name_lower>_ed25519` (private key) and `ssh_keys/<machine_name_lower>_ed25519.pub` (public key)
   - Inspect `ssh_keys/` to see if any key pairs already exist. Ask the user to confirm the derived defaults (`machine_hostname` and SSH key name) or override them (e.g., choosing an existing key pair in `ssh_keys/`).
   - **Important**: Never generate SSH keys automatically via `ssh-keygen`. The user always places both the private key (`ssh_keys/<key_name>`) and public key (`ssh_keys/<key_name>.pub`) in `ssh_keys/` manually.

## Step 2: Host Connection & Authentication Settings (`secrets.yml`)

All host-specific private parameters and secrets for a machine live in a local gitignored YAML file at `machines/<MACHINE_NAME>/secrets.yml` using clean unprefixed lowercase `snake_case` names:

1. **Connection Details (Always Ask Directly)**:
   - Always ask the user for the machine's **IP address (`machine_ip`)**, **SSH username (`machine_ssh_user`)**, and optional **SSH port (`machine_ssh_port`)** (defaulting to `21979`, with automatic fallback to port `22` during first-time bootstrap in `scripts/run-machine.sh`).
   - Write these provided values directly into `machines/<MACHINE_NAME>/secrets.yml`.
2. **Optional Password Parameters**:
   - Ask the user whether this machine requires:
     - **Initial SSH Password (`machine_ssh_pass`)**: Needed only if password authentication is used before the SSH public key is authorized.
     - **Sudo / Privilege Escalation Password (`machine_become_pass`)**: Needed only if the remote user requires a password for `sudo`.
   - Only include `ansible_ssh_pass: "{{ machine_ssh_pass }}"` and/or `ansible_become_pass: "{{ machine_become_pass }}"` in `inventory.yml` (and `secrets.yml`) if the user indicates they are needed.
   - For any required passwords (`machine_ssh_pass`, `machine_become_pass`), ask if the user wants to provide them in chat or fill in empty `machine_*_pass: ""` stubs in `machines/<MACHINE_NAME>/secrets.yml` manually.

## Step 3: Baseline & Module Selection

1. **Baseline Settings (`ansible/roles/baseline`)**:
   - `baseline` is mandatory and always runs first.
   - Read [ansible/roles/baseline/defaults/main.yml](file:///Users/alfredomorresi/Documents/develop/sysadm-agent/ansible/roles/baseline/defaults/main.yml).
   - Ask the user for `baseline_timezone` (default recommendation: `Europe/Rome`) and whether they want to customize any default `baseline` settings (such as `baseline_enable_node_exporter` or `baseline_sshd_password_auth`). Otherwise, rely on `baseline/defaults/main.yml` without duplicating unchanged defaults in `vars.yml`.
2. **Composable Modules (`ansible/roles/`)**:
   - Dynamically list the existing directories under `ansible/roles/` (excluding `baseline`). Only allow selecting modules that already exist in `ansible/roles/`.
   - Ask the user which additional modules to enable on `<MACHINE_NAME>`.
   - For each selected module, dynamically read `ansible/roles/<module>/defaults/main.yml` and ask the user if they want to override any of its default variables in `vars.yml` (placing any sensitive or private module parameters in `machines/<MACHINE_NAME>/secrets.yml` as `<module_name>_<param>`).

## Step 4: Generate Machine Files (`machines/<MACHINE_NAME>/`)

Create or update the following files inside `machines/<MACHINE_NAME>/`:

### 1. `machines/<MACHINE_NAME>/inventory.yml` *(committed)*
Include `ansible_ssh_pass` and `ansible_become_pass` only if requested in Step 2:
```yaml
all:
  hosts:
    <MACHINE_NAME>:
      ansible_host: "{{ machine_ip }}"
      ansible_port: "{{ machine_ssh_port | default(21979, true) | int }}"
      ansible_user: "{{ machine_ssh_user }}"
      # Include only when initial SSH password is required:
      # ansible_ssh_pass: "{{ machine_ssh_pass }}"
      # Include only when sudo password is required:
      # ansible_become_pass: "{{ machine_become_pass }}"
      ansible_ssh_private_key_file: "{{ playbook_dir }}/../../ssh_keys/<key_name>"
```

### 2. `machines/<MACHINE_NAME>/vars.yml` *(committed)*
Both `ssh_keys/<key_name>` (in `inventory.yml`) and `ssh_keys/<key_name>.pub` (in `vars.yml`) are required so `baseline` always ensures the public key is authorized in `~/.ssh/authorized_keys`:
```yaml
---
machine_hostname: "<hostname>"
baseline_timezone: "<timezone>"
baseline_ssh_pub_key_file: "{{ playbook_dir }}/../../ssh_keys/<key_name>.pub"

# Include any customized public baseline or module-specific variables below
```

### 3. `machines/<MACHINE_NAME>/playbook.yml` *(committed)*
Loads both `vars.yml` and `secrets.yml`, and tags each role with its module name so selective module runs (`--tags <module>`) are supported:
```yaml
---
- name: Configure machine <MACHINE_NAME>
  hosts: <MACHINE_NAME>
  become: true
  vars_files:
    - vars.yml
    - secrets.yml
  roles:
    - role: baseline
      tags: [baseline]
    # Followed by selected existing modules from ansible/roles/, e.g.:
    # - role: rainbowhat
    #   tags: [rainbowhat]
```

### 4. `machines/<MACHINE_NAME>/secrets.yml` *(gitignored)* & `logs/.gitkeep`
- Ensure `machines/<MACHINE_NAME>/logs/.gitkeep` exists.
- Create or update the local gitignored `machines/<MACHINE_NAME>/secrets.yml` with the machine's private parameters:
```yaml
---
# Private parameters and secrets for machine <MACHINE_NAME> (gitignored)
machine_ip: "<ip_address>"
machine_ssh_port: 21979
machine_ssh_user: "<ssh_user>"
# Include only when requested:
# machine_ssh_pass: ""
# machine_become_pass: ""
```

## Step 5: Verify `secrets.yml` & SSH Keys Loop

1. Run the validation script:
   ```bash
   python3 scripts/check-env.py <MACHINE_NAME>
   ```
2. If `scripts/check-env.py` reports any `[MISSING]` parameters in `machines/<MACHINE_NAME>/secrets.yml` or missing SSH key files (`ssh_keys/<key_name>` or `ssh_keys/<key_name>.pub`):
   - Clearly list the missing items and pause to let the user place the key pair in `ssh_keys/` (with `chmod 600 ssh_keys/<key_name>`) and/or fill in `machines/<MACHINE_NAME>/secrets.yml`.
   - Once the user confirms they have added them, re-run `python3 scripts/check-env.py <MACHINE_NAME>` until it exits with `0` (`[SUCCESS]`).
