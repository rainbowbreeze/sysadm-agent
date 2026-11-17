# `baseline` — Mandatory Base System & SSH Hardening Module

## Overview
The `baseline` module is the mandatory first role executed on every target machine (`Debian`/`Ubuntu`, `Alpine`, and `TechNexion i.MX Release Distro`). It configures:
1. System hostname (`machine_hostname`), timezone (`baseline_timezone`), and optional headless mode (`baseline_disable_gui`, default `false`).
2. Passwordless SSH public key authorization (`~{{ ansible_user }}/.ssh/authorized_keys` from `baseline_ssh_pub_key_file`).
3. Optional APT GPG signing keys (`baseline_apt_gpg_keys`), package upgrades (`baseline_upgrade_packages`), package cache cleanup (`baseline_clean_package_cache`), and an automatic reboot when packages are upgraded (`baseline_reboot_after_upgrade`, default `true`) on `Debian` and `Alpine` with a graceful 180s manual-power-cycle rescue (`baseline_reboot_rescue_timeout: 180`).
4. Baseline observability utilities (`htop`, `iotop`, `curl`, `jq`, `lsof`, `sysstat`, `iproute2`) and optional Prometheus `node_exporter` (`baseline_enable_node_exporter`) on `Debian` and `Alpine` (automatically skipped on `TechNexion i.MX Release Distro`, which ships a fixed Yocto rootfs without remote package feeds).
5. **`sshd` hardening** via `/etc/ssh/sshd_config.d/00-sysadm-agent.conf` on port `21979` (`baseline_sshd_port`), with `PermitRootLogin` (`baseline_sshd_permit_root_login`, defaulting to `"prohibit-password"` when `ansible_user == 'root'` and `"no"` otherwise) and `PasswordAuthentication` (`baseline_sshd_password_authentication`, default `"no"`), plus systemd socket activation port override (`/etc/systemd/system/sshd.socket.d/00-sysadm-agent.conf`) on `TechNexion i.MX Release Distro`, followed by an automatic connection switch and runtime verification via `sshd -T`.

## Headless Mode (`baseline_disable_gui`)
- Default: `baseline_disable_gui: false` (restores `graphical.target` if `display-manager.service` or `weston.service` is enabled and the machine was previously set to `multi-user.target`; leaves headless servers untouched).
- When `baseline_disable_gui: true`:
  1. Checks if the machine is already headless (`systemctl get-default` == `multi-user.target` and display manager / `weston.service` is not active).
  2. If `systemctl get-default` is not `multi-user.target` (e.g., `graphical.target`), switches the default target to `multi-user.target`.
  3. If a display manager or Wayland compositor (`slim`, `lightdm`, `gdm`, `sddm`, `weston`) is active, stops it immediately.

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

On socket-activated OpenSSH systems (`TechNexion i.MX Release Distro` using `sshd.socket`), `baseline` also deploys `/etc/systemd/system/sshd.socket.d/00-sysadm-agent.conf` (`ListenStream=` reset followed by `ListenStream=21979`). When `baseline_sshd_password_authentication` is `"no"` (default), `AuthenticationMethods publickey` is enforced. After restarting `ssh`/`sshd`/`sshd.socket` and switching the active Ansible connection to `baseline_sshd_port`, `baseline` runs `sshd -T` to assert that the effective runtime settings match the configured baseline policy.
