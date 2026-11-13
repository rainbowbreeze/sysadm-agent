# sysadm-agent

An AI-Agent-Native system administrator powered by **Ansible** and **Agent Skills** (`ai-sysadm-*`) to install, configure, and maintain Linux machines on a network idempotently.

## Available Skills (`.agents/skills/`)

| Skill | File | Description |
| :--- | :--- | :--- |
| **`ai-sysadm-configure-machine`** | [SKILL.md](./.agents/skills/ai-sysadm-configure-machine/SKILL.md) | Interactively defines or updates a machine configuration under `machines/<MACHINE_NAME>/` via a series of questions (host connection info, SSH key pair in `ssh_keys/`, `baseline` settings, and composable modules), generates `machines/<MACHINE_NAME>/secrets.yml`, and verifies readiness with `scripts/check-env.py`. |
| **`ai-sysadm-provision-machine`** | [SKILL.md](./.agents/skills/ai-sysadm-provision-machine/SKILL.md) | Validates pre-flight requirements (`.venv`, `machines/<MACHINE_NAME>/secrets.yml`, `ssh_keys/`), executes Ansible (`scripts/run-machine.sh <MACHINE_NAME>`) across all or selected (`--tags`) modules, and records installation logs inside `machines/<MACHINE_NAME>/logs/history.md`. |
| **`ai-sysadm-create-module`** | [SKILL.md](./.agents/skills/ai-sysadm-create-module/SKILL.md) | Scaffolds or updates a self-contained, idempotent Ansible role in `ansible/roles/<module_name>/` (such as `<category>_<variant>` hardware/service modules for `Debian`/Ubuntu and `Alpine`) and presents all configured defaults and required secrets for confirmation. |

## Documentation

- **[AGENTS.md](./AGENTS.md)**: Core operational invariants, architecture conventions, per-machine `machines/<MACHINE_NAME>/secrets.yml` management, `ssh_keys/` management, and CLI reference.
