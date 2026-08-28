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

## What it reports

| Event | `incident_type` |
|-------|-----------------|
| Entity → `unavailable`/`unknown` | `state_change` |
| Battery crosses below threshold | `battery_low` |
| Entity → `problem` | `system_problem` |
| `update` entity → `on` | `update_available` |
| HA repair registry update | `repair_event` |
| Recovery events | `state_recovery`, `battery_recovered`, `problem_cleared`, `update_installed` |

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
