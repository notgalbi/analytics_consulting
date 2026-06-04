"""
data_loader.py — Reads CSV or Excel files into a DataFrame with basic metadata.
"""
from __future__ import annotations

import io

import pandas as pd
from pathlib import Path


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def load_file(uploaded_file) -> tuple[pd.DataFrame, dict]:
    """
    Load a Streamlit UploadedFile into a DataFrame.
    Returns (dataframe, metadata_dict).
    """
    filename = uploaded_file.name
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {SUPPORTED_EXTENSIONS}")

    try:
        if ext == ".csv":
            df = _load_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, engine="openpyxl" if ext == ".xlsx" else "xlrd")
    except Exception as e:
        raise RuntimeError(f"Failed to read '{filename}': {e}") from e

    metadata = _build_metadata(df, filename)
    return df, metadata


def load_from_bytes(content: bytes, filename: str) -> tuple[pd.DataFrame, dict]:
    """
    Load a CSV or Excel file from raw bytes — drop-in for load_file() when
    the source is Google Drive or any non-Streamlit upload.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {SUPPORTED_EXTENSIONS}")
    try:
        if ext == ".csv":
            df = _load_csv_bytes(content)
        else:
            df = pd.read_excel(
                io.BytesIO(content),
                engine="openpyxl" if ext == ".xlsx" else "xlrd",
            )
    except Exception as e:
        raise RuntimeError(f"Failed to read '{filename}': {e}") from e
    return df, _build_metadata(df, filename)


def _load_csv(uploaded_file) -> pd.DataFrame:
    """Try common encodings so we don't crash on non-UTF-8 files."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Could not decode the CSV file with any common encoding.")


def _load_csv_bytes(content: bytes) -> pd.DataFrame:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Could not decode the CSV file with any common encoding.")


def _build_metadata(df: pd.DataFrame, filename: str) -> dict:
    """Summarise column names and dtypes — no raw row data."""
    dtype_map = {col: str(df[col].dtype) for col in df.columns}
    return {
        "filename": filename,
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
        "dtypes": dtype_map,
    }
