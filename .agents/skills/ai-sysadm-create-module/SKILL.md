---
name: ai-sysadm-create-module
description: >-
  Use this skill when the user wants to create or update a composable
  Ansible configuration module (role) in `ansible/roles/<module_name>/`, such as
  a hardware-specific camera module (`camera_<type>`), a display module, or a
  sensor/service module.
---

# AI-Sysadm: Create or Update Module (`ai-sysadm-create-module`)

Follow this workflow when creating or updating a composable configuration module in `ansible/roles/<module_name>/`.

> **Strict Isolation Rule**: When creating or updating a module, scope all changes strictly to `ansible/roles/<module_name>/`. **Never modify** existing machine folders (`machines/<MACHINE_NAME>/`).

## Step 1: Design & Naming Rules

1. **Self-Contained Role Naming (`<category>_<variant>`)**:
   - Use lowercase letters and underscores only.
   - For hardware or service variants, create one self-contained role per variant using `<category>_<variant>` (e.g., `camera_rpicam`, `camera_usb`, `screen_hdmi`) rather than a single umbrella role, so each module is independently selectable in `playbook.yml`.
2. **Idempotency**:
   - Always use declarative Ansible modules (`ansible.builtin.package`, `ansible.builtin.template`, `ansible.builtin.lineinfile`, `ansible.builtin.copy`, `ansible.builtin.service`, `ansible.builtin.user`, `ansible.builtin.pip`).
   - If `ansible.builtin.command` or `ansible.builtin.shell` is unavoidable, always guard it with `creates:`, `changed_when:`, and `failed_when:`.
3. **Target OS Scope (`Debian` / `Alpine`)**:
   - Target machines run **Debian/Ubuntu (`Debian`)** and/or **Alpine (`Alpine`)**.
   - Determine which OS family(ies) the module supports (`["Debian", "Alpine"]`, `["Debian"]`, or `["Alpine"]`).
   - Always start `tasks/main.yml` with an `ansible.builtin.assert` checking `ansible_os_family` against the module's supported OS list so execution fails fast on an unsupported distro.
   - Only create `vars/Debian.yml` and/or `vars/Alpine.yml` when package or service names differ between supported OS families.
4. **Single Source of Truth Documentation in `defaults/main.yml`**:
   - Do **not** create separate `README.md` files inside roles.
   - Document the module's purpose, supported `ansible_os_family` values, configurable `<module_name>_*` variables, and required secret parameters (defined in a machine's `machines/<MACHINE_NAME>/secrets.yml`) in a structured comment header at the top of `ansible/roles/<module_name>/defaults/main.yml` so `ai-sysadm-configure-machine` can discover everything from `defaults/main.yml`.
5. **Private Parameters Convention (`machines/<MACHINE_NAME>/secrets.yml`)**:
   - Never hardcode credentials, IPs, or secrets inside a role.
   - Expose role variables in `defaults/main.yml` prefixed with `<module_name>_`, and document in the header of `defaults/main.yml` which `<module_name>_*` variables must be provided in `machines/<MACHINE_NAME>/secrets.yml` (and referenced in `machines/<MACHINE_NAME>/vars.yml` if needed).

## Step 2: Scaffold Immediately & Present Values for Confirmation/Editing

1. **Scaffold the Role Files**:
   Immediately scaffold or update `ansible/roles/<module_name>/` based on the user's prompt:
   ```text
   ansible/roles/<module_name>/
   ├── defaults/
   │   └── main.yml       # Structured header comments + <module_name>_* defaults
   ├── vars/              # Optional: only when supporting multiple OS families with different package/service names
   │   ├── Debian.yml     # Debian & Ubuntu
   │   └── Alpine.yml     # Alpine Linux
   ├── tasks/
   │   └── main.yml       # OS assert + idempotent tasks
   ├── handlers/          # Optional: service restart/reload handlers
   │   └── main.yml
   └── templates/         # Optional: Jinja2 configuration templates
   ```

   **Template for `defaults/main.yml`**:
   ```yaml
   ---
   # Module: <module_name>
   # Description: <Brief description of what this module installs and configures>
   # Supported OS Families: Debian, Alpine
   # Required Secrets (in machines/<MACHINE_NAME>/secrets.yml):
   #   - <module_name>_<secret_name> (or "None")

   <module_name>_example_setting: true
   ```

   **Template for `tasks/main.yml` OS Check**:
   ```yaml
   ---
   - name: Verify target OS is supported by <module_name>
     ansible.builtin.assert:
       that:
         - ansible_os_family in ["Debian", "Alpine"]
       fail_msg: "Module <module_name> only supports Debian/Ubuntu and Alpine (found {{ ansible_os_family }})."
   ```

2. **Show All Values for User Confirmation or Editing**:
   Present a clear summary of all scaffolded values to the user and ask if they want to confirm or edit any of them:
   - **Module Name & Path**: `ansible/roles/<module_name>/`
   - **Supported OS Families**: e.g., `Debian` (Debian/Ubuntu), `Alpine`
   - **Default Variables (`defaults/main.yml`)**: All `<module_name>_*` keys and their default values
   - **Required Secrets (`machines/<MACHINE_NAME>/secrets.yml`)**: Any `<module_name>_*` secrets a machine's `secrets.yml` will need to supply
   - **Tasks & Handlers**: Summary of packages, configuration files, and services managed

## Step 3: Verification & Documentation Sync

1. **Syntax / Lint Verification**:
   - If `.venv/bin/ansible-lint` is installed, run `.venv/bin/ansible-lint ansible/roles/<module_name>/` to verify role structure and idempotency practices.
2. **Documentation Sync**:
   - Update [AGENTS.md](file:///Users/alfredomorresi/Documents/develop/sysadm-agent/AGENTS.md) only if core architectural conventions or how the project works changed (never add a module catalog to `AGENTS.md`).
