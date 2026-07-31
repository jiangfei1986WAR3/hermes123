# MTU-KEX Timeout: Canonical Log Pattern

## The Tell-Tale Signature

When a user can't SSH in but the server looks perfectly configured, look for this pattern:

### Server-side SSH logs (`journalctl -u ssh`)

```
Jul 22 17:47:22 host sshd[38609]: Timeout before authentication for connection from 123.139.26.46 to 172.21.39.242, pid = 78856
Jul 22 17:47:48 host sshd[38609]: Timeout before authentication for connection from 123.139.26.46 to 172.21.39.242, pid = 78886
Jul 22 17:55:22 host sshd[2794]: Timeout before authentication for connection from 123.139.26.46 to 172.21.39.242, pid = 3103
... (repeats exactly every ~120s = LoginGraceTime)
```

**Critical**: There are NO `Failed password for root from 123.139.26.46` entries between these timeouts. The client never reached the auth prompt.

Meanwhile, attacker IPs show normal behavior:
```
Jul 22 18:31:16 sshd-session[11070]: Failed password for root from 91.92.40.200 port 38996 ssh2
```

### TCP connection state (`ss -tnp`)

```
ESTAB  0  0  172.21.39.242:22  123.139.26.46:1850  users:(("sshd-session",pid=11766,fd=9))
```

Connection is ESTABLISHED but the process shows `[accepted]` — TCP handshake done, SSH KEX never completed.

### Historical context

The same IP successfully connected earlier:
```
Jul 22 07:57:28 sshd-session[48001]: Accepted password for root from 123.139.26.46 port 4414 ssh2
```

Then later that day, all attempts from the same IP started timing out — suggesting a network path change (different WiFi, VPN, ISP routing).

### Network config

```
eth0: mtu 1400  ← non-standard (default is 1500)
```

## Why This Happens

1. SSH begins with a TCP 3-way handshake → succeeds (small ~60-byte packets)
2. SSH then performs key exchange (KEX) → sends larger packets (~1400+ bytes)
3. If the path MTU between client and server is smaller than the server's MTU, and PMTUD ICMP "fragmentation needed" messages are blocked by a firewall:
   - Large packets are silently dropped
   - SSH hangs waiting for KEX to complete
   - After LoginGraceTime (default 120s), the server logs `Timeout before authentication`
4. The client never gets to the password prompt because KEX never finished
