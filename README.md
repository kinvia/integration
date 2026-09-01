# Kinvia — Home Assistant Integration

Proactive incident reporting from Home Assistant to [Kinvia](https://github.com/kinvia/infrastructure). Home Assistant sends raw incident data; Kinvia evaluates priority dynamically using server-side rules (Smart Core).

## Install via HACS

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/kinvia/integration` (category: **Integration**)
3. Search **Kinvia** → **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration → Kinvia**

## Manual install

Copy `custom_components/kinvia/` into your Home Assistant `config/custom_components/` directory and restart HA.

## Configuration

| Setting | Description |
|---------|-------------|
| **Kinvia base URL** | Origin without `/api/...` and without trailing slash (e.g. `https://kinvia.example.com` or `http://localhost:3000` for dev) |
| **Inbound Webhook Secret** | From Kinvia → Installations → your installation → Webhook Secret |
| **Monitored domains** | Domains watched for disconnections and system problems |
| **Excluded entities** | Entities to ignore (e.g. `sun.sun`) |
| **Battery threshold** | Report when battery entities cross below this % (default 15) |
| **Startup grace period** | Minutes after HA startup to suppress `state_change` and `state_recovery` noise (default 10; 0 = disabled) |
| **Report baseline state** | After grace period, report entities still in a problematic state (default on) |

## What it reports

| Event | `incident_type` |
|-------|-----------------|
| Entity → `unavailable`/`unknown` | `state_change` |
| Battery crosses below threshold | `battery_low` |
| Entity → `problem` | `system_problem` |
| `update` entity → `on` | `update_available` |
| HA repair registry update | `repair_event` (`details.action`: `create`, `update`, or `remove`) |
| Recovery events | `state_recovery`, `battery_recovered`, `problem_cleared`, `update_installed` |

### Repairs (Spook / HA Repairs panel)

The integration listens to `repairs_issue_registry_updated` and forwards the full event (including `action`) in `details`. Kinvia closes tickets when `action` is `remove` (issue deleted from the registry after a successful fix).

- **Fix** in the Repairs UI (flow that deletes the issue) → `remove` → Kinvia should close the ticket.
- **Ignore** in the Repairs UI → `update` only; the issue stays in the registry → ticket remains open until the issue is actually fixed.
- Every **15 minutes**, Kinvia reconciles against the live issue registry and sends synthetic `remove`/`create` payloads if bus events were missed (e.g. webhook failure).

Check HA logs for `Kinvia repair event` and `Kinvia repair reconcile` after fixing or ignoring repairs.

### Startup grace period

On Home Assistant restart, hundreds of entities may briefly report `unavailable` or `unknown` while integrations and devices reconnect. To avoid flooding Kinvia with incidents:

1. The integration waits for `EVENT_HOMEASSISTANT_STARTED` before listening to state changes.
2. During the **startup grace period** (default 10 minutes), `state_change` and `state_recovery` incidents are suppressed.
3. When grace ends, an optional **baseline** reports only entities that had suppressed transitions during grace and are **still** unavailable (not `unknown`), low battery, in `problem` state, or with pending updates.

If you add the integration while HA is already running, grace and baseline are skipped and monitoring starts immediately.

Webhook: `POST {base_url}/api/v1/webhooks/incidents` with header `x-api-key: {webhook_secret}`.

During setup, the integration validates credentials **without creating tickets**:

1. `GET {base_url}/health` — confirms the Kinvia server is reachable
2. `GET {base_url}/api/v1/webhooks/health` with `x-api-key` — confirms the webhook secret is valid

## Development

```bash
pip install -r requirements-dev.txt
pytest tests/
```

## Releases

CI validates every PR (`hassfest`, HACS, `pytest`). To publish a release:

```bash
python3 scripts/bump_version.py   # bumps patch in manifest.json
git add custom_components/kinvia/manifest.json
git commit -m "chore: release vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

Create a GitHub Release from the tag so HACS users can pick a version.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Invalid API key` | Regenerate webhook secret in Kinvia, reconfigure integration |
| Connection refused | Dev: port **3000**. Production: port **4200** or HTTPS |
| No tickets | Check HA logs for `custom_components.kinvia` |
