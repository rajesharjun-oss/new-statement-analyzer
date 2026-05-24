# Project Structure

This repository now keeps the runnable product code separate from legacy debugging material.

## Product Code

- `backend/` contains the FastAPI service, extraction engines, categorization, validation, OCR helpers, and Excel export code.
- `components/`, `services/`, `App.tsx`, and `index.tsx` contain the React frontend.
- `Dockerfile`, `docker-compose.yml`, and `vite.config.ts` define local and container runtime behavior.

## Diagnostics

- `tools/diagnostics/legacy-root/` contains older root-level debugging and verification scripts.
- `tools/diagnostics/legacy-backend/` contains older backend-specific forensic scripts.

These scripts are kept for reference because bank-statement extraction bugs often need historical probes. They are not part of the runtime path.

## Debug Artifacts

- `artifacts/debug-output/` is for generated logs, text dumps, screenshots, and other extraction artifacts.
- The folder is ignored by git so large or sensitive statement-derived output does not keep accumulating in commits.

## Regression Fixtures

- `tests/regression/expected_statements.json` stores expected counts and totals for local sample statements.
- `tests/regression/run_regression.py` runs those expectations against the backend extractor.

Statement files are ignored by git. Keep real PDFs/spreadsheets local and point the expectations file at them.
