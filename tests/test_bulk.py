# tests/test_bulk.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
import respx
import httpx
import tempfile
client = TestClient(app)
HOSP_BASE = "https://hospital-directory.onrender.com"

@respx.mock
def test_bulk_success(tmp_path):
    csv_content = "name,address,phone\nHospital A,1 Main St,12345\nHospital B,2 Side St,\n"
    file_path = tmp_path / "h.csv"
    file_path.write_text(csv_content)
    respx.post(f"{HOSP_BASE}/hospitals/").mock(return_value=httpx.Response(201, json={'id': 101}))
    respx.patch(f"{HOSP_BASE}/hospitals/batch/").mock(return_value=httpx.Response(200, json={'activated': True}))
    with open(file_path, "rb") as f:
        resp = client.post("/hospitals/bulk", files={"file": ("h.csv", f, "text/csv")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_hospitals"] == 2
