# Local Deploy

[← Back to README](../README.md)

Scripts for running tychos as a long-lived local service on a Mac, exposed to the internet via [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) and gated by [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/) (email allowlist).

This is the only documented production deployment path. The bare API server has open registration and no built-in access control — running it without an external auth gate exposes a fully-open admin to whoever can reach the URL.

## What gets installed

- Two `launchd` agents (`com.tychos.server`, `com.tychos.worker`) that keep the FastAPI server and the background worker running across reboots
- A Cloudflare Tunnel ingress rule mapping `<subdomain>.<domain>` to `http://127.0.0.1:<TYCHOS_PORT>`
- A DNS CNAME for the hostname pointing at the tunnel
- A Cloudflare Access self-hosted application + email allowlist policy

## Prerequisites

- macOS (uses `launchctl`)
- A Cloudflare account with the target domain
- A Cloudflare API token with `Account: Cloudflare Tunnel: Edit`, `Zone: DNS: Edit`, `Account: Access: Apps and Policies: Edit` permissions
- `cloudflared`, `node`, `npm`, `python3`, `jq`, `openblas` (for scipy on Python 3.14+) installed via Homebrew
- Python 3.14 or compatible

## First-time setup

1. **Copy the example env file** and fill in your Cloudflare details:
   ```bash
   cp local_deploy/.env.example local_deploy/.env
   $EDITOR local_deploy/.env
   ```

   Required values:
   - `CF_API_TOKEN` — Cloudflare API token (see permissions above)
   - `CF_ACCOUNT_ID`, `CF_ZONE_ID` — your Cloudflare account & zone IDs
   - `CF_DOMAIN`, `CF_SUBDOMAIN` — the public URL pieces (e.g. `tychos` + `example.com` → `tychos.example.com`)
   - `CF_ACCESS_EMAILS` — comma-separated list of email addresses allowed through Cloudflare Access
   - `TYCHOS_DIR` — absolute path to your tychos checkout
   - `TYCHOS_PORT` — local port the FastAPI server should bind to (e.g. `8000`)

2. **Run setup:**
   ```bash
   ./local_deploy/setup.sh
   ```

   This is a 9-step script that:
   1. Validates required env vars
   2. Sets up the Python venv inside `tychos_skyfield/.venv` and installs server + scientific deps
   3. Builds the admin SPA (`admin/dist/`)
   4. Initializes the database (runs migrations + seed)
   5. Verifies the Cloudflare API token
   6. Detects an existing cloudflared service or creates a new tunnel + installs cloudflared
   7. Adds an ingress rule for the tychos hostname
   8. Creates the DNS CNAME
   9. Creates (or updates) the Zero Trust Access app + email allowlist policy
   10. Installs and bootstraps the two launchd agents

   Setup is idempotent — re-running it picks up new emails in `CF_ACCESS_EMAILS`, refreshes ingress, and restarts the agents.

## Re-running

```bash
./local_deploy/setup.sh    # idempotent — re-applies env, refreshes Cloudflare config, restarts agents
./local_deploy/restart.sh  # just restart the launchd agents (doesn't touch Cloudflare)
```

## Tearing down

```bash
./local_deploy/teardown.sh
```

This:
- Unloads the launchd agents and removes their plists
- Removes the tychos hostname from the tunnel ingress (preserves other rules)
- Deletes the DNS CNAME
- Deletes the Cloudflare Access app

It deliberately leaves the cloudflared service installed (it may be shared with other apps) and does **not** delete the database under `results/`.

For a full teardown that also deletes the tunnel and uninstalls cloudflared:

```bash
./local_deploy/teardown.sh --full
```

Use `--full` only if tychos was the only thing using the tunnel.

## Files

| File | Purpose |
|---|---|
| `setup.sh` | First-time install + idempotent re-runs |
| `teardown.sh` | Reverse setup; `--full` also deletes tunnel + uninstalls cloudflared |
| `restart.sh` | Restart the two launchd agents without touching Cloudflare |
| `com.tychos.server.plist` | Template launchd plist for the API server (variables get substituted at install time) |
| `com.tychos.worker.plist` | Template launchd plist for the background worker |
| `.env.example` | Template for the env file you fill in |
| `.env` | Your local config (gitignored) |
