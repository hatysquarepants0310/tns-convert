# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
python3 tns_converter_app.py   # Web UI at http://localhost:8051
```

Only dependency: `cryptography` (`pip install cryptography`).

## Architecture: how a `.tns` file is processed

`tns_converter_app.py` is a single standalone file — all library code is inlined. A `.tns` file is a modified ZIP container processed through these layers (all inside the app):

1. **TNS outer parser** — parses the ZIP structure (handles TI's custom `*TIMLP` header and `TIPD` EOCD signature instead of standard `PK`). Returns `TnsEntry` objects.
2. **Method 13 crypto** — decrypts method-13 entries (TI's proprietary compression: 3DES-ECB header decrypt → raw deflate → TIXC stream).
3. **TIXC decode/encode** — converts between TIXC0100 (TI's binary XML token format) and plain UTF-8 XML.
4. **Converter logic** — parses the resulting XML to extract notes (`fmtxt` inside `urn:TI.Notepad`) or spreadsheet data (`urn:tabulator` columns).

Writing a `.tns` reverses the process: XML → TIXC encode → method 13 encrypt → ZIP with `*TIMLP0601` first-entry header + `TIPD` EOCD.

## TNS file structure

Every `.tns` has at least two XML entries:
- `Document.xml` — calculator settings/metadata (must be first, uses `*TIMLP` header)
- `Problem1.xml` — actual content (notes or spreadsheet)

**Notes** use `xmlns:np="urn:TI.Notepad"`. Text lives inside `<np:fmtxt>` as XML-escaped `<r2dtotree>` markup with `<leaf name="1word">` tokens per word.

**Spreadsheets** use `xmlns:tb="urn:tabulator"`. Data lives in `<tb:column type="cell-column">` elements; formulas are stored without the leading `=` (TI-Nspire syntax).

## Formula translation

Excel `=A1+B1` ↔ TNS `A1+B1` (strip/add `=`). `=SUM(A1:A5)` ↔ `SUM(A1:A5)`. Handled in `_format_cell_value` and `extract_spreadsheet_data`.

## XLSX support

XLSX read/write is implemented from scratch using `zipfile` + `xml.etree` — no openpyxl dependency. Only supports flat tabular data with formulas.
