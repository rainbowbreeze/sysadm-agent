#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <machine_name> [extra-ansible-playbook-args...]" >&2
  exit 1
fi

MACHINE_NAME="$1"
shift

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MACHINE_DIR="$REPO_ROOT/machines/$MACHINE_NAME"
INVENTORY_FILE="$MACHINE_DIR/inventory.yml"
PLAYBOOK_FILE="$MACHINE_DIR/playbook.yml"
LOGS_DIR="$MACHINE_DIR/logs"

if [[ ! -d "$MACHINE_DIR" ]]; then
  echo "[ERROR] Machine folder not found: $MACHINE_DIR" >&2
  exit 1
fi

if [[ ! -f "$INVENTORY_FILE" || ! -f "$PLAYBOOK_FILE" ]]; then
  echo "[ERROR] Missing inventory.yml or playbook.yml in $MACHINE_DIR" >&2
  exit 1
fi

# Load local .env if present
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

# Verify required environment variables and ssh_keys/ before running Ansible
python3 "$REPO_ROOT/scripts/check-env.py" "$MACHINE_NAME"

# Auto-detect initial bootstrap port (22 -> 21979) unless running --syntax-check
if [[ " $* " != *" --syntax-check "* ]]; then
  IP_VAR="${MACHINE_NAME}_IP"
  PORT_VAR="${MACHINE_NAME}_SSH_PORT"
  TARGET_IP="${!IP_VAR:-}"
  TARGET_PORT="${!PORT_VAR:-21979}"

  if [[ -n "$TARGET_IP" && "$TARGET_PORT" != "22" ]]; then
    if ! python3 -c "import socket, sys; s = socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2); s.close()" "$TARGET_IP" "$TARGET_PORT" 2>/dev/null; then
      if python3 -c "import socket, sys; s = socket.create_connection((sys.argv[1], 22), timeout=2); s.close()" "$TARGET_IP" 2>/dev/null; then
        echo "=== [BOOTSTRAP] Port $TARGET_PORT is not open on $TARGET_IP yet, but port 22 is reachable. Using port 22 for initial bootstrap ==="
        export "${PORT_VAR}=22"
      fi
    fi
  fi
fi

# Prepare machine logs directory
mkdir -p "$LOGS_DIR"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOGS_DIR/ansible-${TIMESTAMP}.log"

export ANSIBLE_CONFIG="$REPO_ROOT/ansible.cfg"
export ANSIBLE_LOG_PATH="$LOG_FILE"

# Locate ansible-playbook binary (prefer local .venv)
if [[ -x "$REPO_ROOT/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE_PLAYBOOK="$REPO_ROOT/.venv/bin/ansible-playbook"
elif command -v ansible-playbook >/dev/null 2>&1; then
  ANSIBLE_PLAYBOOK="$(command -v ansible-playbook)"
else
  echo "[ERROR] ansible-playbook not found. Install it in .venv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "=== Running Ansible for machine '$MACHINE_NAME' ==="
echo "=== Log file: $LOG_FILE ==="

set +e
"$ANSIBLE_PLAYBOOK" -i "$INVENTORY_FILE" "$PLAYBOOK_FILE" --diff "$@"
EXIT_CODE=$?
set -e

ln -sf "$(basename "$LOG_FILE")" "$LOGS_DIR/latest.log"
echo "=== Execution finished (exit code: $EXIT_CODE). Log saved to: $LOG_FILE ==="
exit "$EXIT_CODE"
