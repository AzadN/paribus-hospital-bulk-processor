# Paribus - Hospital Bulk Processor

This repository contains a production-minded FastAPI implementation for the Paribus coding challenge:
- Accepts CSV uploads at `/hospitals/bulk`
- Creates hospital records at the external hospital directory API
- Activates batch and returns a detailed processing summary

## Files included
- `app/` - FastAPI application
- `tests/` - pytest tests (uses respx to mock HTTP)
- `Dockerfile`, `docker-compose.yml`
- `requirements.txt`
- `DEPLOYMENT.md` - instructions for deploying to Render
- `GIT_INIT.sh` - commands to initialize a git repo with meaningful commits
- Original assignment PDF included for reference:
  - `Senior_Python_Developer_Assignment_Paribus.pdf`

## Quick start (local)
1. Create virtualenv, install:
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

2. Run:
   uvicorn app.main:app --reload --port 8000

3. Upload CSV via:
   curl -F "file=@hospitals.csv;type=text/csv" http://localhost:8000/hospitals/bulk

## Tests
pytest

