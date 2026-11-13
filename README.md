# sysadm-agent

An AI-Agent-Native system administrator powered by **Ansible** and **Agent Skills** (`ai-sysadm-*`) to install, configure, and maintain Linux machines on a network idempotently.

## Available Skills (`_agents/skills/`)

| Skill | File | Description |
| :--- | :--- | :--- |
| **`ai-sysadm-configure-machine`** | [SKILL.md](./_agents/skills/ai-sysadm-configure-machine/SKILL.md) | Interactively defines or updates a machine configuration under `machines/<MACHINE_NAME>/` via a series of questions (host connection info, SSH key pair in `ssh_keys/`, `baseline` settings, and composable modules), populates local `.env`, and verifies readiness with `scripts/check-env.py`. |
| **`ai-sysadm-provision-machine`** | [SKILL.md](./_agents/skills/ai-sysadm-provision-machine/SKILL.md) | Validates pre-flight requirements (`.venv`, env vars, `ssh_keys/`), executes Ansible (`scripts/run-machine.sh <MACHINE_NAME>`) across all or selected (`--tags`) modules, and records installation logs inside `machines/<MACHINE_NAME>/logs/history.md`. |
| **`ai-sysadm-create-module`** | [SKILL.md](./_agents/skills/ai-sysadm-create-module/SKILL.md) | Scaffolds or updates a self-contained, idempotent Ansible role in `ansible/roles/<module_name>/` (such as `<category>_<variant>` hardware/service modules for `Debian`/Ubuntu and `Alpine`) and presents all configured defaults and required env vars for confirmation. |

## Documentation

- **[AGENTS.md](./AGENTS.md)**: Core operational invariants, architecture conventions, `<MACHINE_NAME>_<SERVICE>_<VALUE>` environment variable rules, `ssh_keys/` management, and CLI reference.
