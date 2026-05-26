# tnstools

Pure Python tools for decoding and rebuilding TI-Nspire `.tns` documents.

`tnstools` converts TI-Nspire documents to readable XML and builds working
method 13 `.tns` files back from XML without Firebird, emulator RAM dumps, or a
runtime dependency on `phoenix.dll`.

## Features

- Parse TI-Nspire's ZIP-like `.tns` container, including `*TIMLP####` and
  `TIPD` records.
- Extract `Document.xml`, `Problem1.xml`, and other XML entries.
- Decode entry methods:
  - method 0 stored/raw
  - method 8 deflate
  - method 13 TI envelope
- Decode method 13 in pure Python:
  - fixed-key 3DES header decrypt
  - `TIEN0100` parse
  - derived 3DES counter-mode body decrypt
  - raw deflate
  - `TIXC0100` expansion to XML
- Encode XML back to method 13 `.tns` files:
  - XML to `TIXC0100`
  - raw deflate
  - method 13 3DES envelope
  - rebuilt `.tns` container
- Batch validation with optional `phoenix.dll` compatibility checks.

## Requirements

- Python 3.10 or newer
- `pycryptodome`

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

or:

```powershell
python -m pip install pycryptodome
```

For editable development installs:

```powershell
python -m pip install -e .
```

That exposes the `tnstools` and `tns-to-xml` console commands.

## Decode `.tns` to XML

```powershell
python tnstools.py -tns path\to\file.tns
```

This writes a folder named after the input file:

```text
file.tns.xml\
  Document.xml
  Problem1.xml
```

Choose an output folder explicitly:

```powershell
python tnstools.py -tns path\to\file.tns -out out_xml
```

List entries while decoding:

```powershell
python tnstools.py -tns path\to\file.tns --list
```

Write diagnostic artifacts:

```powershell
python tnstools.py -tns path\to\file.tns --artifacts
```

Artifacts include an entry manifest and intermediate `.tixc` streams. They are
for debugging, not required for normal use.

## Build XML Back To `.tns`

```powershell
python tnstools.py -xml file.tns.xml -out rebuilt.tns
```

This is an independent encode path. It does not need the original `.tns`:

```text
raw XML -> TIXC0100 -> raw deflate -> method 13 -> TNS container
```

The rebuilt `.tns` checksum and size can differ from the original. That is
expected because the tool creates fresh TIXC, deflate, and method 13 bytes. The
compatibility target is decoded XML identity and successful loading in TI
software.

Verify after building:

```powershell
python tnstools.py -xml file.tns.xml -out rebuilt.tns --verify
```

## Batch Validation

Create a validation folder and put `.tns` files in it:

```powershell
mkdir validation
copy path\to\*.tns validation\
python tnstools.py --validate validation
```

Validation performs:

```text
.tns -> XML -> rebuilt .tns -> XML
```

and compares the XML bytes.

If TI-Nspire Student Software is installed, also check rebuilt files with
TI's own TIXC expander:

```powershell
python tnstools.py --validate validation --validate-phoenix
```

`phoenix.dll` is only an optional compatibility oracle. It is not needed for
normal decoding or encoding.

## Compatibility Notes

Validated locally against documents covering:

- Program Editor UDFs
- Scratchpad/calculator history
- Lists & Spreadsheet/tabulator XML
- DataGrapher/graph XML
- ScriptApp/Lua CDATA payloads
- older CX-era and newer CX/CX II-era documents
- game/program-style documents

Known caveats:

- New or unusual `TIXC0100` states may still need support.
- Non-XML resources embedded in `.tns` files are preserved only when supported by
  the current container path.
- This project does not include TI OS images, TI DLLs, or copyrighted sample
  documents.

## Optional Phoenix Comparison

The old comparison backend can decode with TI-Nspire Student Software's
`phoenix.dll` when installed:

```powershell
python tnstools.py -tns file.tns -out out_xml --tixc-backend phoenix
```

You can provide a path if needed:

```powershell
python tnstools.py -tns file.tns -out out_xml --tixc-backend phoenix --phoenix "C:\Path\to\phoenix.dll"
```

Copied standalone `phoenix.dll` files often fail to load because their
dependencies are missing. The installed Student Software layout is more
reliable.

## Development

Compile-check the scripts:

```powershell
python -m py_compile tnstools.py tns_to_xml.py tns_outer_parse.py tns_method13.py tixc_decode.py tixc_encode.py
```

Run validation on a private corpus:

```powershell
python tnstools.py --validate validation --validate-phoenix
```

The repository intentionally ignores `.tns`, `.tns.xml`, generated rebuilds,
reverse-engineering databases, and TI DLLs.

Detailed reverse-engineering notes are kept in
[docs/REVERSE_NOTES.md](docs/REVERSE_NOTES.md).

## Legal

This repository contains original interoperability code only. Do not commit or
redistribute TI OS images, TI DLLs, commercial documents, or other proprietary
materials.
