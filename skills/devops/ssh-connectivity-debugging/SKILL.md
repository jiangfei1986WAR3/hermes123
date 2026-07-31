---
name: ssh-connectivity-debugging
description: Systematic SSH connectivity debugging — diagnose why SSH to a server works or fails, covering server-side config, network path, MTU/KEX issues, and log-driven root cause analysis.
category: devops
---

# SSH Connectivity Debugging

Systematic workflow for diagnosing why SSH connections succeed or fail. Covers the full chain: server daemon, firewall, PAM, SSH config, network path, and client-side issues.

## Triggers

- "I can't SSH into the server"
- "SSH connection hangs / times out"
- "Connection refused" or "Connection reset"
- Any SSH connectivity complaint

## Diagnostic Workflow (in order)

### Phase 1: Server-Side Sanity

Run these in parallel — they're all independent:

```bash
# 1. Is sshd running?
systemctl status sshd || systemctl status ssh

# 2. Is the port listening?
ss -tlnp | grep ':22\b'

# 3. Local firewall?
iptables -L -n; ufw status; firewall-cmd --list-all 2>/dev/null

# 4. Effective SSH config (NOT the raw config file — this resolves Include/drops)
sshd -T | grep -iE '(passwordauth|permitrootlogin|pubkeyauth|port|listen)'

# 5. Raw config for Include ordering
grep -v '^#' /etc/ssh/sshd_config | grep -v '^$'
for f in /etc/ssh/sshd_config.d/*.conf; do echo "=== $f ==="; cat "$f" 2>/dev/null; done
```

**Key pitfall**: `sshd -T` shows the resolved effective config. The raw config file may have `PasswordAuthentication no` AFTER an `Include` that sets it to `yes` — the effective value is what matters. Always run `sshd -T`, don't guess from config files.

### Phase 2: Check Logs for the User's IP

```bash
# Recent SSH activity for the user's IP
journalctl -u ssh --since "2 hours ago" --no-pager | grep '<USER_IP>'

# Broader: any recent failures or successes
journalctl -u ssh --since "1 hour ago" --no-pager | grep -iE '(Accepted|Failed|Timeout|error)'
```

### Phase 3: Identify the Failure Mode by Log Pattern

The logs tell you EXACTLY where the connection died. Match the pattern:

| Log Pattern | What Happened | Likely Cause |
|---|---|---|
| `Timeout before authentication` with **NO** `Failed password` | TCP connected but client never sent auth | **MTU/KEX problem** — SSH handshake packets dropped |
| `Timeout before authentication` + `Failed password` | TCP connected, client tried auth, failed | Wrong password or brute-force attack |
| `Connection closed by <IP>` | Client actively disconnected | User cancelled, or client-side timeout |
| `read ECONNRESET` (client side) | Server reset the connection | Firewall, MTU clamping gone wrong, or per-source penalty |
| No log entry at all for the IP | Connection never reached sshd | External firewall / security group / network routing |
| `Accepted password/key` | Auth succeeded | The problem is elsewhere (shell, PTY, client) |

### Phase 4: The MTU / KEX Timeout Pattern (CRITICAL)

**When you see**: `Timeout before authentication` from the user's IP with ZERO `Failed password` entries, BUT the attacker IPs (if any) show `Failed password` normally — AND `ss -tnp` shows ESTABLISHED connections from the user's IP in `[accepted]` state.

**Root cause**: SSH key exchange (KEX) packets exceed the path MTU. TCP 3-way handshake succeeds (small packets), but KEX negotiation sends larger packets that get silently dropped because PMTUD (Path MTU Discovery) ICMP messages are blocked somewhere in the network path.

**Indicators**:
- `ip addr` shows non-standard MTU (e.g. 1400 instead of 1500) on the server NIC
- User connected successfully before (e.g. earlier that day or from a different network)
- Multiple `Timeout before authentication` entries, each exactly `LoginGraceTime` (default 120s) apart
- `ss -tnp | grep <IP>` shows ESTABLISHED but no auth progress

**Fix attempts (in order of preference)**:

1. **MSS clamping via iptables** — least invasive, may or may not work:
   ```bash
   # MTU 1400 → MSS = 1400 - 40 = 1360
   iptables -A OUTPUT -p tcp --tcp-flags SYN,RST SYN -o <iface> -j TCPMSS --set-mss 1360
   ```
   ⚠️ If this causes `ECONNRESET` instead of timeout, remove it immediately.

2. **Fallback: switch to key-based auth + provide the key out-of-band** — side-steps the KEX problem if the client's SSH can negotiate a smaller KEX:
   ```bash
   ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" -C "recovery-key"
   cat /root/.ssh/id_ed25519.pub >> /root/.ssh/authorized_keys
   # Deliver private key to user via base64 encoding
   base64 /root/.ssh/id_ed25519
   ```

3. **Adjust server MTU** — if the cloud provider allows it:
   ```bash
   ip link set dev eth0 mtu 1500
   ```

4. **Reduce SSH KEX algorithm to force smaller packets** (advanced, rarely needed):
   Add to `/etc/ssh/sshd_config`:
   ```
   KexAlgorithms curve25519-sha256
   ```

### Phase 5: Additional Checks

```bash
# Check for per-source penalties (OpenSSH 9.5+)
sshd -T | grep -i persource

# Check PAM configuration
cat /etc/pam.d/sshd

# Check authorized_keys (0-byte file = no keys configured)
ls -la /root/.ssh/authorized_keys

# Check for fail2ban or hosts.deny blocks
fail2ban-client status sshd 2>/dev/null
cat /etc/hosts.deny

# Public IP of the server
curl -s https://api.ipify.org
```

## Key Commands Reference

| Command | What it reveals |
|---|---|
| `sshd -T \| grep -i <keyword>` | **Effective** SSH config (resolved) |
| `ss -tnp \| grep ':22'` | Current TCP connections + recv-q/send-q |
| `journalctl -u ssh --since "X" --no-pager` | SSH daemon logs with timestamps |
| `passwd -S root` | Account status (P = password set, L = locked) |
| `iptables -L -n` | Active firewall rules |

## Pitfalls

- **Config Include ordering**: `Include /etc/ssh/sshd_config.d/*.conf` on line 24 but `PasswordAuthentication no` on line 149 — the later line wins for single-value directives. Always trust `sshd -T` output over config-file reading.
- **MSS clamping can backfire**: Setting MSS too low or on the wrong chain can cause `ECONNRESET`. Test and remove immediately if it makes things worse.
- **authorized_keys being 0 bytes**: Check file size, not just existence. `ls -la` reveals a 0-byte file that looks valid but contains no keys.
- **Cloud security groups**: Even if everything on the server is correct, the cloud provider's security group may block the port or the user's IP. You can't check this from inside the server — ask the user to verify their cloud console.
- **VS Code Remote SSH vs plain SSH**: VS Code's SSH extension uses its own transport (ssh2.js), loads local identity keys, and may not fall back to password auth. Always test with plain `ssh` CLI first to isolate the issue.
