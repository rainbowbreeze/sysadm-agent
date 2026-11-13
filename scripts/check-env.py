#!/usr/bin/env python3
"""Validate environment variables and SSH keys for a target machine folder."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

# Matches lookup('env', 'VAR_NAME' ...) or lookup("env", "VAR_NAME" ...)
ENV_LOOKUP_RE = re.compile(
    r"""lookup\(\s*['"]env['"]\s*,\s*['"]([^'"]+)['"]([^)]*)\)"""
)
# Matches references to ssh_keys/<filename> in YAML files
SSH_KEY_REF_RE = re.compile(r"""ssh_keys/([A-Za-z0-9._-]+)""")
VALID_ENV_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def load_dotenv(dotenv_path: Path) -> dict[str, str]:
    """Parse a simple .env file without external dependencies."""
    env_vars: dict[str, str] = {}
    if not dotenv_path.is_file():
        return env_vars

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env_vars[key] = value
    return env_vars


def scan_machine_files(machine_dir: Path) -> tuple[list[tuple[str, bool, str]], list[str]]:
    """Return ([(env_var, is_required, file_name), ...], [ssh_key_rel_paths])."""
    env_refs: list[tuple[str, bool, str]] = []
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

            for match in ENV_LOOKUP_RE.finditer(line):
                var_name = match.group(1)
                lookup_tail = match.group(2)
                # Required if default=undef(...) is used or if no `| default(` fallback is on the line
                is_required = "undef(" in lookup_tail or "| default(" not in line
                if var_name not in seen_vars:
                    seen_vars.add(var_name)
                    env_refs.append((var_name, is_required, yaml_name))

            for key_match in SSH_KEY_REF_RE.finditer(line):
                key_name = key_match.group(1)
                if key_name == ".gitkeep":
                    continue
                rel_key = f"ssh_keys/{key_name}"
                if rel_key not in ssh_keys:
                    ssh_keys.append(rel_key)

    return env_refs, ssh_keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify required environment variables and SSH keys for a machine."
    )
    parser.add_argument("machine", help="Machine folder name under machines/")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    machine_dir = repo_root / "machines" / args.machine

    if not machine_dir.is_dir():
        print(f"[ERROR] Machine directory not found: {machine_dir}", file=sys.stderr)
        return 1

    dotenv_vars = load_dotenv(repo_root / ".env")
    combined_env = {**dotenv_vars, **os.environ}

    env_refs, ssh_keys = scan_machine_files(machine_dir)

    print(f"=== Checking configuration for machine: {args.machine} ===")
    has_errors = False

    if not env_refs:
        print("  [INFO] No lookup('env', ...) references found.")
    else:
        print("\nEnvironment Variables:")
        for var_name, is_required, source_file in env_refs:
            if not VALID_ENV_NAME_RE.match(var_name):
                print(
                    f"  [INVALID NAME] {var_name} (in {source_file}) -> "
                    "Must use only underscores '_', letters, and digits."
                )
                has_errors = True
                continue

            val = combined_env.get(var_name, "")
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
            f"[FAILED] Missing required environment variables or SSH keys for '{args.machine}'.\n"
            "Please add the missing values to your local .env file or ssh_keys/ directory.",
            file=sys.stderr,
        )
        return 1

    print(f"[SUCCESS] All required environment variables and SSH keys for '{args.machine}' are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
