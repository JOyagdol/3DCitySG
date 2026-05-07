# v1 Measurement Runbook

This runbook defines reproducible steps for generating latest benchmark and profiling outputs.

Command source of truth:
1. `docs/command_cheatsheet.md`

History documents:
1. `docs/experiment_results_history.md`
2. `docs/dataset_result_history.md`

## 1. Goal

1. Generate benchmark output (`benchmark_report.json`)
2. Generate profiling output (`import_profile_report.json`)
3. Update latest documents only (`experiment_results.md`, `dataset_result_comparison.md`)

## 2. Prerequisites

1. Project root:
   - `C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG`
2. Conda environment:
   - `3DCitySG`
3. Neo4j:
   - running locally
   - matches `configs/default.yaml`

## 3. Workflow

Use this runbook for sequence only. Use `docs/command_cheatsheet.md` for exact commands.

1. Run `refresh_latest_reports.py` with dataset tag.
2. Verify:
   - benchmark `query_failed=0`
   - profile `runs_failed=0`
3. Update latest-only docs.
4. Move replaced rows/sections to history docs.

## 4. Completion Checklist

1. `Import complete` in logs
2. Latest artifacts are timestamped with dataset tag
3. Latest docs updated:
   - `docs/experiment_results.md`
   - `docs/dataset_result_comparison.md`
4. Old values moved:
   - `docs/experiment_results_history.md`
   - `docs/dataset_result_history.md`
