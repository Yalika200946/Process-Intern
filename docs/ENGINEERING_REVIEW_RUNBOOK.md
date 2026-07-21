# Engineering Review Runbook

**Status:** CURRENT — REVIEW MODE

## Release sequence

1. Confirm the raw input file and record its source/date.
2. Review governance registries; do not edit a status to `APPROVED` without source,
   approver, approval date, applicable range, and review date.
3. Run `python -m pytest -q`.
4. Run `python pipeline/run_all.py --timeout 1800`.
5. Confirm the command exits zero and reports an immutable generation ID.
6. Open the generation's `run_manifest.json`; validation must pass and every
   required artifact must share the same generation ID.
7. Start `python backend/server.py` and verify the dashboard review-mode banner.
8. Review cleaning candidates, assumptions, topology flags, model fallback, and
   economic scenarios before presenting recommendations.

## Failure handling

- Notebook/post failure: the previous published pointer remains active.
- Publish validation failure: do not copy files manually into the active snapshot;
  resolve the error and rerun.
- Mixed generation warning: stop using the dashboard for decisions and rerun the
  full pipeline.
- Unresolved topology or plant-limit item: retain candidate/assumption status and
  request engineering confirmation.
- Cleaning event without a maintenance record: keep it as a candidate. A local
  review decision is append-only and does not rewrite the detected event.

## Approval boundary

Review-ready means software integrity and traceability are verified. It does not
mean the plant has approved the physical-property correlation, topology, limits,
clean reference, event history, priority weights, forecast horizon, or economics.
