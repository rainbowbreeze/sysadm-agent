#!/usr/bin/env python3
"""Validate per-machine secrets.yml and SSH keys for a target machine folder."""

from __future__ import annotations

import argparse
import re
import stat
import sys
from pathlib import Path

# Matches Jinja2 variable expressions like {{ machine_ip }} or {{ machine_ssh_port | default(21979) }}
JINJA_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*([^}]*)\}\}")
# Matches references to ssh_keys/<filename> in YAML files
SSH_KEY_REF_RE = re.compile(r"""ssh_keys/([A-Za-z0-9._-]+)""")
VALID_VAR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

ANSIBLE_BUILTIN_VARS = {
    "playbook_dir",
    "inventory_dir",
    "inventory_hostname",
    "inventory_hostname_short",
    "ansible_os_family",
    "ansible_distribution",
    "item",
    "hostvars",
    "groups",
    "group_names",
}


def load_simple_yaml(yaml_path: Path) -> dict[str, str]:
    """Parse a flat YAML key-value file without requiring external dependencies."""
    if not yaml_path.is_file():
        return {}

    raw_text = yaml_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(raw_text)
        if isinstance(loaded, dict):
            return {
                str(k): ("" if v is None else str(v))
                for k, v in loaded.items()
            }
    except Exception:
        pass

    result: dict[str, str] = {}
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "---":
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        # Strip inline comment if not quoted
        if value and value[0] not in ("'", '"') and " #" in value:
            value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def scan_machine_files(
    machine_dir: Path, public_vars: dict[str, str]
) -> tuple[list[tuple[str, bool, str]], list[str]]:
    """Return ([(secret_var, is_required, file_name), ...], [ssh_key_rel_paths])."""
    secret_refs: list[tuple[str, bool, str]] = []
    seen_vars: set[str] = set()
    ssh_keys: list[str] = []

    for yaml_name in ("inventory.yml", "vars.yml", "playbook.yml"):
        yaml_path = machine_dir / yaml_name
        if not yaml_path.is_file():
            continue
        content = yaml_path.read_text(encoding="utf-8")

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            for match in JINJA_VAR_RE.finditer(line):
                var_name = match.group(1)
                expr_tail = match.group(2)
                if var_name in ANSIBLE_BUILTIN_VARS or var_name in public_vars:
                    continue
                is_required = "| default(" not in expr_tail and "|default(" not in expr_tail
                if var_name not in seen_vars:
                    seen_vars.add(var_name)
                    secret_refs.append((var_name, is_required, yaml_name))

            for key_match in SSH_KEY_REF_RE.finditer(line):
                key_name = key_match.group(1)
                if key_name == ".gitkeep":
                    continue
                rel_key = f"ssh_keys/{key_name}"
                if rel_key not in ssh_keys:
                    ssh_keys.append(rel_key)

    return secret_refs, ssh_keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify required secrets.yml variables and SSH keys for a machine."
    )
    parser.add_argument("machine", help="Machine folder name under machines/")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    machine_dir = repo_root / "machines" / args.machine
    secrets_path = machine_dir / "secrets.yml"
    vars_path = machine_dir / "vars.yml"

    if not machine_dir.is_dir():
        print(f"[ERROR] Machine directory not found: {machine_dir}", file=sys.stderr)
        return 1

    public_vars = load_simple_yaml(vars_path)
    secret_vars = load_simple_yaml(secrets_path)
    # Remove self-referential expressions from public_vars
    defined_public_vars = {
        k: v for k, v in public_vars.items() if "{{" not in v
    }

    secret_refs, ssh_keys = scan_machine_files(machine_dir, defined_public_vars)

    print(f"=== Checking configuration for machine: {args.machine} ===")
    has_errors = False

    print(f"\nSecrets File (machines/{args.machine}/secrets.yml):")
    if not secrets_path.is_file():
        print(f"  [MISSING FILE] machines/{args.machine}/secrets.yml not found")
        has_errors = True
    else:
        print(f"  [OK]      machines/{args.machine}/secrets.yml exists")

    if not secret_refs:
        print("  [INFO] No secret variable references found.")
    else:
        print("\nPrivate Parameters (in secrets.yml):")
        for var_name, is_required, source_file in secret_refs:
            if not VALID_VAR_NAME_RE.match(var_name):
                print(
                    f"  [INVALID NAME] {var_name} (in {source_file}) -> "
                    "Must use lowercase snake_case ('a-z', '0-9', '_')."
                )
                has_errors = True
                continue

            val = secret_vars.get(var_name, "")
            is_set = bool(val)
            req_label = "REQUIRED" if is_required else "OPTIONAL"
            if is_set:
                print(f"  [OK]      {var_name} ({req_label}, referenced in {source_file})")
            elif is_required:
                print(f"  [MISSING] {var_name} ({req_label}, referenced in {source_file})")
                has_errors = True
            else:
                print(f"  [UNSET]   {var_name} ({req_label}, referenced in {source_file})")

    if ssh_keys:
        print("\nSSH Keys (ssh_keys/):")
        for rel_key in ssh_keys:
            key_path = repo_root / rel_key
            if not key_path.is_file():
                print(f"  [MISSING] {rel_key} -> File not found at {key_path}")
                has_errors = True
            else:
                mode = stat.S_IMODE(key_path.stat().st_mode)
                if not rel_key.endswith(".pub") and (mode & 0o077) != 0:
                    print(
                        f"  [WARNING] {rel_key} exists but permissions are {oct(mode)} "
                        f"(run: chmod 600 {rel_key})"
                    )
                else:
                    print(f"  [OK]      {rel_key}")

    print()
    if has_errors:
        print(
            f"[FAILED] Missing required parameters in machines/{args.machine}/secrets.yml or SSH keys in ssh_keys/.\n"
            f"Please update machines/{args.machine}/secrets.yml or ssh_keys/ before provisioning.",
            file=sys.stderr,
        )
        return 1

    print(f"[SUCCESS] All required parameters in secrets.yml and SSH keys for '{args.machine}' are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
