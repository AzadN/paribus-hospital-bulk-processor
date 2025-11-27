# app/main.py
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
    row: int
    hospital_id: Optional[int] = None
    name: Optional[str] = None
    status: str

class BulkResponse(BaseModel):
    batch_id: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float
    batch_activated: bool
    hospitals: List[HospitalRowResult]

async def post_hospital(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
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
