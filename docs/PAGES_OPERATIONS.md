# GitHub Pages Closed Loop

KMB GitHub Pages is an operational dashboard, not a static introduction page.

## Closed loop

```text
AI-A/B/C/D/E
→ canonical data / research / review / recovery
→ material-change trigger
→ src/kmb_lab/pages.py
→ web/index.html + web/status.json
→ Pages artifact
→ deploy
→ public URL verification
→ source_commit + generated_at verification
```

The public layer never fabricates missing market or agent evidence. Missing inputs remain `UNKNOWN`, `MISSING`, or `NOT COLLECTED`. A repository agent file that says `ACTIVE` is not sufficient evidence of healthy execution; heartbeat and produced output are cross-checked, and conflicts render as `STATE MISMATCH` / `DEGRADED`.

Push deployment is limited to user-visible material state. A scheduled 10-minute watchdog compares the live `status.json` material fingerprint with the current repository fingerprint and rebuilds only when they differ.

A Pages change is not complete at commit time. The deploy job verifies the public URL, exact `source_commit`, non-empty `generated_at`, and the same source commit embedded in public `index.html`.

Pages failure is a LOCAL display-layer incident. It must not disable collectors, research, schedulers, or AI-A/B/C/D/E.

Every agent preflight checks: five-agent survival → dead/stale agent recovery → data freshness → Pages freshness → Pages deploy → queue → review-board → specialty work.
