"""Unit tests for CSV parsing and validation helpers used by the hospital bulk processor.

These tests are pure unit tests (no HTTP calls, no httpx, no FastAPI TestClient).
They exercise CSV header normalization, row-count limits, phone regex behavior,
and basic per-row validation/whitespace normalization logic.
Docstring style matches app/main.py (concise / PEP257).
"""

import pytest
from app.main import phone_re, MAX_ROWS
import csv
import io


# -----------------------------
# Helper: parse simple CSV text
# -----------------------------
def parse_csv_text(text: str):
    """Parse CSV text into a list of normalized row dicts and return original fieldnames.

    Normalizes header names to lowercase and strips whitespace from values.

    Args:
        text: CSV content as a string.

    Returns:
        Tuple of (rows, fieldnames) where rows is a list of dicts and fieldnames is the
        original header list from csv.DictReader.
    """
    reader = csv.DictReader(io.StringIO(text))
    return [
        {k.lower().strip(): (v or "").strip() for k, v in row.items()}
        for row in reader
    ], reader.fieldnames


# -----------------------------
# 1. Test CSV header normalization
# -----------------------------
def test_csv_parse_normalizes_headers():
    """Headers are normalized to lowercase and values are stripped of surrounding whitespace."""
    csv_text = "Name , Address , Phone\nA,St,123\n"
    rows, headers = parse_csv_text(csv_text)

    assert list(rows[0].keys()) == ["name", "address", "phone"]
    assert rows[0]["name"] == "A"
    assert rows[0]["address"] == "St"
    assert rows[0]["phone"] == "123"


# -----------------------------
# 2. Missing required columns
# -----------------------------
def test_missing_required_columns():
    """Detect when required CSV columns (name, address) are absent."""
    csv_text = "wrong,headers\nx,y\n"

    rows, headers = parse_csv_text(csv_text)

    headers_lower = [h.lower().strip() for h in headers]

    required = {"name", "address"}
    missing = not required.issubset(set(headers_lower))

    assert missing is True


# -----------------------------
# 3. More than allowed rows
# -----------------------------
def test_exceeds_max_rows():
    """Ensure parsing can detect when the CSV contains more rows than MAX_ROWS."""
    rows_csv = "\n".join([f"A{i},St{i},123" for i in range(MAX_ROWS + 5)])
    csv_text = "name,address,phone\n" + rows_csv

    rows, _ = parse_csv_text(csv_text)

    assert len(rows) > MAX_ROWS
    assert len(rows) == MAX_ROWS + 5


# -----------------------------
# 4. Valid phone number format
# -----------------------------
def test_valid_phone_regex():
    """Verify that a set of known-good phone strings match the phone regex."""
    valid_numbers = [
        "+1 234-567-8901",
        "1234567",
        "+91 9876543210",
        "555 5555",
    ]
    for number in valid_numbers:
        assert phone_re.match(number)


# -----------------------------
# 5. Invalid phone number format
# -----------------------------
def test_invalid_phone_regex():
    """Verify that malformed phone strings do not match the phone regex."""
    invalid_numbers = [
        "abcde",
        "12ab34",
        "!@#$%",
        "phone123",
    ]
    for number in invalid_numbers:
        assert not phone_re.match(number)


# -----------------------------
# 6. Row missing required fields
# -----------------------------
def test_missing_name_or_address():
    """Rows missing either name or address are considered invalid."""
    rows = [
        {"name": "", "address": "Street", "phone": "123"},
        {"name": "X", "address": "", "phone": "123"},
        {"name": "", "address": "", "phone": ""},
    ]

    def invalid(row):
        return not row.get("name") or not row.get("address")

    assert invalid(rows[0]) is True
    assert invalid(rows[1]) is True
    assert invalid(rows[2]) is True


# -----------------------------
# 7. Normalize whitespace
# -----------------------------
def test_normalize_whitespace():
    """Whitespace around header values and cells is stripped during parsing."""
    csv_text = "name,address,phone\n  A  ,  St Road ,  555  \n"
    rows, _ = parse_csv_text(csv_text)

    assert rows[0]["name"] == "A"
    assert rows[0]["address"] == "St Road"
    assert rows[0]["phone"] == "555"
