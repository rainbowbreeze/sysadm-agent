# `baseline` — Mandatory Base System & SSH Hardening Module

## Overview
The `baseline` module is the mandatory first role executed on every target machine (`Debian`/`Ubuntu` and `Alpine`). It configures:
1. System hostname (`machine_hostname`), timezone (`baseline_timezone`), and optional headless mode (`baseline_disable_gui`, default `false`).
2. Passwordless SSH public key authorization (`~{{ ansible_user }}/.ssh/authorized_keys` from `baseline_ssh_pub_key_file`).
3. Optional APT GPG signing keys (`baseline_apt_gpg_keys`), package upgrades (`baseline_upgrade_packages`), package cache cleanup (`baseline_clean_package_cache`), and an automatic reboot when packages are upgraded (`baseline_reboot_after_upgrade`, default `true`) with a graceful 180s manual-power-cycle rescue (`baseline_reboot_rescue_timeout: 180`).
4. Baseline observability utilities (`htop`, `iotop`, `curl`, `jq`, `lsof`, `sysstat`, `iproute2`) and optional Prometheus `node_exporter` (`baseline_enable_node_exporter`).
5. **`sshd` hardening** via `/etc/ssh/sshd_config.d/00-sysadm-agent.conf` on port `21979` (`baseline_sshd_port`), with `PermitRootLogin` (`baseline_sshd_permit_root_login`, default `"no"`) and `PasswordAuthentication` (`baseline_sshd_password_authentication`, default `"no"`), followed by an automatic connection switch and runtime verification via `sshd -T`.

## Headless Mode (`baseline_disable_gui`)
- Default: `baseline_disable_gui: false` (leaves existing boot target and display manager untouched).
- When `baseline_disable_gui: true`:
  1. Checks if the machine is already headless (`systemctl get-default` == `multi-user.target` and `display-manager.service` is not active).
  2. If `systemctl get-default` is not `multi-user.target` (e.g., `graphical.target`), switches the default target to `multi-user.target`.
  3. If `display-manager.service` (e.g., `slim`, `lightdm`, `gdm`) is active, stops it immediately so `Xorg` and desktop sessions are terminated without needing a reboot.

## SSH Hardening (`/etc/ssh/sshd_config.d/00-sysadm-agent.conf`)
Instead of modifying the vendor `/etc/ssh/sshd_config` file directly, `baseline` deploys `/etc/ssh/sshd_config.d/00-sysadm-agent.conf` (loaded first via `Include /etc/ssh/sshd_config.d/*.conf` so OpenSSH's first-match-wins rule takes precedence over any cloud-init or vendor drop-ins):

```ssh-config
Port 21979
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
AuthenticationMethods publickey
```

When `baseline_sshd_password_authentication` is `"no"` (default), `AuthenticationMethods publickey` is enforced. After restarting `ssh`/`sshd` and switching the active Ansible connection to `baseline_sshd_port`, `baseline` runs `sshd -T` to assert that the effective runtime settings match the configured baseline policy.
