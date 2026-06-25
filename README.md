# TnsTools

Pure Python tools for decoding and rebuilding TI-Nspire `.tns` documents.

Converts TI-Nspire documents to readable XML and builds working method 13
`.tns` files back from XML — no Firebird, emulator RAM dumps, or `phoenix.dll`
required.

## Installation

**Requirements:** Python 3.10+

```bash
pip install -r requirements.txt
```

Or install as an editable package:

```bash
pip install -e .
```

This exposes the `tnstools` and `tns-to-xml` console commands. The only
dependency is [`pycryptodome`](https://pypi.org/project/pycryptodome/).

## Quick Start

### Decode a `.tns` file to XML

```bash
python tnstools.py -tns myfile.tns
```

Creates a folder `myfile.tns.xml/` with the extracted XML files
(`Document.xml`, `Problem1.xml`, etc.).

### Build a `.tns` file from XML

```bash
python tnstools.py -xml myfile.tns.xml -out rebuilt.tns
```

Takes an XML folder and produces a working `.tns` file with method 13
encryption.

## Usage

### Decoding (`.tns` → XML)

```bash
# Basic decode
python tnstools.py -tns file.tns

# Choose output folder
python tnstools.py -tns file.tns -out my_output

# List entries while decoding
python tnstools.py -tns file.tns --list

# Write diagnostic artifacts (TIXC streams, entry manifest)
python tnstools.py -tns file.tns --artifacts
```

### Encoding (XML → `.tns`)

```bash
# Build .tns from XML folder
python tnstools.py -xml file.tns.xml -out rebuilt.tns

# Build and verify the result
python tnstools.py -xml file.tns.xml -out rebuilt.tns --verify
```

The rebuilt file may differ in bytes from the original (fresh encoding), but
the decoded XML will be identical.

### Batch Validation

Validate multiple `.tns` files with a decode → encode → decode roundtrip:

```bash
mkdir validation
cp *.tns validation/
python tnstools.py --validate validation
```

Optionally check rebuilt files against TI's own TIXC expander (requires
TI-Nspire Student Software):

```bash
python tnstools.py --validate validation --validate-phoenix
```

### Alternative Decode Command

`tns_to_xml.py` is a simpler wrapper for decoding only:

```bash
python tns_to_xml.py myfile.tns
python tns_to_xml.py myfile.tns output_folder
```

## How It Works

```
Decode:  .tns → method 13 envelope → 3DES decrypt → deflate → TIXC → XML
Encode:  XML → TIXC → deflate → 3DES encrypt → method 13 envelope → .tns
```

Supported compression methods:
- **Method 0** — stored / raw
- **Method 8** — deflate
- **Method 13** — TI proprietary envelope (3DES + TIXC)

## All Options

```
usage: tnstools.py [-h] (-tns FILE | -xml DIR | --validate [DIR])
                   [-out PATH] [--list] [--artifacts] [--verify]
                   [--validate-phoenix] [--allow-stored-xml]
                   [--tixc-backend {auto,pure,phoenix,none}]
                   [--phoenix PATH] [--write-tixc-on-failure]

  -tns FILE              Decode .tns file to XML folder
  -xml DIR               Build .tns file from XML folder
  --validate [DIR]       Validate .tns files in DIR (default: validation/)
  -out PATH              Output path
  --list                 Print parsed entries
  --artifacts            Write diagnostic TIXC streams and manifest
  --verify               Decode rebuilt .tns and compare XML bytes
  --validate-phoenix     Also check with phoenix.dll during validation
  --allow-stored-xml     Write method 0 (stored) instead of method 13
  --tixc-backend TYPE    TIXC backend: auto, pure, phoenix, none
  --phoenix PATH         Path to phoenix.dll (optional)
  --write-tixc-on-failure  Write raw TIXC if XML expansion fails
```

## Compatibility

Tested with documents covering:

- Program Editor UDFs
- Scratchpad / calculator history
- Lists & Spreadsheet
- DataGrapher / graph XML
- ScriptApp / Lua CDATA payloads
- CX-era and CX II-era documents
- Game / program-style documents

## Development

```bash
python -m py_compile tnstools.py tns_to_xml.py tns_outer_parse.py tns_method13.py tixc_decode.py tixc_encode.py
```

Reverse-engineering notes: [docs/REVERSE_NOTES.md](docs/REVERSE_NOTES.md).

## License

[MIT](LICENSE)
