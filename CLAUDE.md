# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
python3 tns_converter_app.py        # Web UI at http://localhost:8051
python3 tns_converter.py input output  # CLI (e.g. notas.tns notas.txt)
```

Only dependency: `cryptography` (`pip install cryptography`).

## Two entry points, one codebase

There are two ways to use this project:

- **`tns_converter_app.py`** — standalone single-file web app. Contains all library code inlined (TIXC decoder/encoder, method 13 crypto, TNS parser, converter logic, HTTP server, and HTML UI). This is what gets released.
- **`tns_converter.py`** — CLI script that imports from `TnsTools/` (a git submodule with the same low-level modules as separate files).

When editing conversion logic, changes likely need to be applied to both `tns_converter.py` and the corresponding section inside `tns_converter_app.py`.

## Architecture: how a `.tns` file is processed

A `.tns` file is a modified ZIP container. Reading one goes through these layers:

1. **`tns_outer_parse.py`** — parses the ZIP structure (handles TI's custom `*TIMLP` header and `TIPD` EOCD signature instead of standard `PK`). Returns `TnsEntry` objects.
2. **`tns_method13.py`** — decrypts method-13 entries (TI's proprietary compression: 3DES-ECB header decrypt → raw deflate → TIXC stream).
3. **`tixc_decode.py` / `tixc_encode.py`** — converts between TIXC0100 (TI's binary XML token format) and plain UTF-8 XML.
4. **Converter logic** (in `tns_converter.py` / the app) — parses the resulting XML to extract notes (`fmtxt` inside `urn:TI.Notepad`) or spreadsheet data (`urn:tabulator` columns).

Writing a `.tns` reverses the process: XML → `encode_tixc` → `encrypt_tixc_to_method13` → ZIP with `*TIMLP0601` first-entry header + `TIPD` EOCD.

## TNS file structure

Every `.tns` has at least two XML entries:
- `Document.xml` — calculator settings/metadata (must be first, uses `*TIMLP` header)
- `Problem1.xml` — actual content (notes or spreadsheet)

**Notes** use `xmlns:np="urn:TI.Notepad"`. Text lives inside `<np:fmtxt>` as XML-escaped `<r2dtotree>` markup with `<leaf name="1word">` tokens per word.

**Spreadsheets** use `xmlns:tb="urn:tabulator"`. Data lives in `<tb:column type="cell-column">` elements; formulas are stored without the leading `=` (TI-Nspire syntax).

## Formula translation

Excel `=A1+B1` ↔ TNS `A1+B1` (strip/add `=`). `=SUM(A1:A5)` ↔ `SUM(A1:A5)`. The converter handles this at the cell level in `_format_cell_value` and `extract_spreadsheet_data`.

## XLSX support

XLSX read/write is implemented from scratch using `zipfile` + `xml.etree` — no openpyxl dependency. The writer (`write_xlsx`) and reader (`read_xlsx`) only support the subset needed for flat tabular data with formulas.
