# Mini Write-up: Design decisions & important notes

## Summary
- Async FastAPI implementation with concurrency controls.
- Per-row validation and clear status codes.
- Retries for transient failures and exponential backoff in production code.
- Batch activation attempted regardless of individual row failures.
- In-memory batch store (dict) used for simplicity as per assignment; swap for Redis/DB for production.

## Why this design?
1. FastAPI + httpx.AsyncClient gives non-blocking concurrency.
2. Semaphore prevents too many concurrent requests to external API.
3. Clear status messages help debugging and acceptance tests.
4. Dockerfile and tests included to make the submission production-ready.

## How to submit
- Push to GitHub with meaningful commits (see GIT_INIT.sh).
- Ensure README explains how to run tests locally.
