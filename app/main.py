"""FastAPI application for bulk processing hospital records.

This module provides a simple API to accept a CSV upload of hospital
rows, validate them, create hospitals via an external hospital-directory
API, and return a per-row report and batch activation status.

Core components:
- Pydantic models describing per-row and batch responses.
- Async HTTP helper with retry/backoff for posting hospitals.
- Endpoint to accept CSV uploads and process rows concurrently with a limit.
- Endpoint to query batch processing status stored in-memory.

Notes:
- Max rows, concurrency, retry/backoff and timeouts are configurable via constants.
- Batches are stored in-memory (the `batches` dict); this is intended for demo/testing.
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import csv
import io
import uuid
import time
import asyncio
import httpx
import re

HOSPITAL_API_BASE = "https://hospital-directory.onrender.com"
MAX_ROWS = 20
CONCURRENT_LIMIT = 5
REQUEST_TIMEOUT = 10.0
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 1.0

app = FastAPI(title="Paribus - Hospital Bulk Processor")
batches: Dict[str, Dict[str, Any]] = {}

phone_re = re.compile(r"^\+?\d[\d\-\s]{3,}$")

class HospitalRowResult(BaseModel):
    """Result record for a single CSV row processed into a hospital.

    Attributes:
        row: 1-based row index from the uploaded CSV.
        hospital_id: ID returned by the hospital API when creation succeeds.
        name: Normalized hospital name provided in the CSV.
        status: Short status string describing the outcome for the row
            (e.g. "created", "invalid_phone_format", "create_failed_500").
    """
    row: int
    hospital_id: Optional[int] = None
    name: Optional[str] = None
    status: str

class BulkResponse(BaseModel):
    """Top-level response model for the bulk create endpoint.

    Attributes:
        batch_id: UUID assigned to this processing batch.
        total_hospitals: Number of rows read from the uploaded CSV.
        processed_hospitals: Number of rows that were processed (attempted).
        failed_hospitals: Number of rows that did not result in creation.
        processing_time_seconds: Elapsed time for the bulk operation.
        batch_activated: Whether the server-side batch activation call returned success.
        hospitals: Per-row results as a list of HospitalRowResult records.
    """
    batch_id: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float
    batch_activated: bool
    hospitals: List[HospitalRowResult]

async def post_hospital(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    """POST a single hospital payload to the external hospital API with retries.

    Uses exponential backoff on transport/read timeouts and retries up to RETRY_ATTEMPTS.

    Args:
        client: An httpx.AsyncClient instance used to make the request.
        payload: JSON-serializable dict describing the hospital.

    Returns:
        httpx.Response returned by the external API.

    Raises:
        httpx.TransportError or httpx.ReadTimeout after exhausting retries.
    """
    url = f"{HOSPITAL_API_BASE}/hospitals/"
    attempt = 0
    while True:
        try:
            resp = await client.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            return resp
        except (httpx.TransportError, httpx.ReadTimeout) as exc:
            attempt += 1
            if attempt >= RETRY_ATTEMPTS:
                raise
            await asyncio.sleep(RETRY_BACKOFF * (2 ** (attempt - 1)))

async def create_hospital_row(semaphore: asyncio.Semaphore, client: httpx.AsyncClient,
                              batch_id: str, row_idx: int, row: dict) -> HospitalRowResult:
    """Validate a CSV row and create a hospital record via the external API.

    Validation performed:
    - `name` and `address` must be present and non-empty.
    - If `phone` is present it must match a basic phone regex.

    This function is concurrency-limited by the provided semaphore to avoid
    overwhelming the external API.

    Args:
        semaphore: asyncio.Semaphore used to limit concurrent HTTP calls.
        client: httpx.AsyncClient used to call the external API.
        batch_id: Identifier for this processing batch attached to created hospitals.
        row_idx: 1-based CSV row index (used for reporting).
        row: Normalized dict of CSV column -> value (lowercased keys).

    Returns:
        HospitalRowResult describing the outcome for the row.
    """
    async with semaphore:
        name = row.get("name", "").strip()
        address = row.get("address", "").strip()
        phone = row.get("phone", "")
        result = HospitalRowResult(row=row_idx, name=name, status="unknown")

        if not name or not address:
            result.status = "invalid_row_missing_name_or_address"
            return result

        if phone:
            phone = phone.strip()
            if not phone_re.match(phone):
                result.status = "invalid_phone_format"
                return result

        payload = {
            "name": name,
            "address": address,
            "creation_batch_id": batch_id
        }
        if phone:
            payload["phone"] = phone

        try:
            resp = await post_hospital(client, payload)
            if resp.status_code in (200, 201):
                body = resp.json()
                result.hospital_id = body.get("id")
                result.status = "created"
            else:
                result.status = f"create_failed_{resp.status_code}"
        except Exception as exc:
            result.status = f"create_exception_{type(exc).__name__}"

        return result

@app.post("/hospitals/bulk", response_model=BulkResponse)
async def upload_bulk_hospitals(file: UploadFile = File(...)):
    """Endpoint to upload a CSV of hospitals and process them in bulk.

    Expected CSV headers (case-insensitive): name,address,phone (phone optional).
    The endpoint enforces MAX_ROWS and will reject overly large uploads.

    Processing steps:
    - Decode CSV and normalize headers to lowercase.
    - Validate presence of required headers.
    - Validate and post each row to the external hospital API concurrently
      up to CONCURRENT_LIMIT tasks at a time.
    - Attempt to activate the batch via the hospital API after creation completes.
    - Store batch metadata/results in the in-memory `batches` dict for later inspection.

    Args:
        file: Uploaded CSV file as FastAPI UploadFile.

    Returns:
        JSONResponse containing the BulkResponse payload describing the batch outcome.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    start_ts = time.time()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not decode file as UTF-8")

    reader = csv.DictReader(io.StringIO(text))
    headers_lower = [h.lower().strip() for h in reader.fieldnames] if reader.fieldnames else []
    required = {"name", "address"}
    if not headers_lower or not required.issubset(set(headers_lower)):
        raise HTTPException(status_code=400, detail="CSV must include headers: name,address,phone (phone optional)")

    rows = []
    for r in reader:
        norm = {k.lower().strip(): (v or "").strip() for k, v in r.items()}
        rows.append(norm)
        if len(rows) > MAX_ROWS:
            raise HTTPException(status_code=400, detail=f"CSV exceeds maximum allowed rows ({MAX_ROWS})")

    total = len(rows)
    batch_id = str(uuid.uuid4())
    batches[batch_id] = {"total": total, "processed": 0, "failed": 0, "results": [], "activated": False}

    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    async with httpx.AsyncClient() as client:
        tasks = [
            create_hospital_row(semaphore, client, batch_id, idx + 1, row)
            for idx, row in enumerate(rows)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        processed = 0
        failed = 0
        out_results = []
        for res in results:
            processed += 1
            if not (res.status and res.status.startswith("created")):
                failed += 1
            out_results.append(res.dict())

        batches[batch_id].update({"processed": processed, "failed": failed, "results": out_results})

        activate_url = f"{HOSPITAL_API_BASE}/hospitals/batch/{batch_id}/activate"
        try:
            act_resp = await client.patch(activate_url, timeout=REQUEST_TIMEOUT)
            batch_activated = act_resp.status_code in (200, 204)
        except Exception:
            batch_activated = False

        batches[batch_id]["activated"] = batch_activated

    elapsed = time.time() - start_ts

    hospitals_out = []
    for r in out_results:
        hospitals_out.append({
            "row": r["row"],
            "hospital_id": r.get("hospital_id"),
            "name": r.get("name"),
            "status": "created_and_activated" if (r.get("status") == "created" and batch_activated) else r.get("status")
        })

    response = {
        "batch_id": batch_id,
        "total_hospitals": total,
        "processed_hospitals": processed,
        "failed_hospitals": failed,
        "processing_time_seconds": round(elapsed, 3),
        "batch_activated": batch_activated,
        "hospitals": hospitals_out
    }
    return JSONResponse(status_code=200, content=response)

@app.get("/hospitals/bulk/{batch_id}/status")
async def bulk_status(batch_id: str):
    """Return current status and a small sample of results for a processing batch.

    Args:
        batch_id: UUID string identifying a previously created batch.

    Returns:
        Dict with batch metadata and up to 10 result records.

    Raises:
        HTTPException(404) if the batch_id is unknown.
    """
    batch = batches.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {
        "batch_id": batch_id,
        "total": batch["total"],
        "processed": batch["processed"],
        "failed": batch["failed"],
        "activated": batch["activated"],
        "results_sample": batch["results"][:10]
    }
