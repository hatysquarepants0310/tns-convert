# TI-Nspire TNS Method 13 Reverse Notes

Date: 2026-05-25

## Current Status

- IDA MCP is working.
- Active IDB: `C:\Users\Administrator\Downloads\flash.i64`
- IDA module: `flash`, imagebase `0x0`
- Auto-analysis ready: yes
- Hex-Rays ready: yes
- `summermaks.tns` is not present on this machine, so validation used available local samples.

The current `tns_to_xml.py` decodes method 13 entries to readable XML without Firebird, without an emulator, without RAM dumps, and without `phoenix.dll` by default. Method 13 crypto, raw deflate, and TIXC expansion are implemented in Python. The old `phoenix.dll` backend is retained only for comparison.

## Strings and Anchors

Flash IDB string hits:

| String | Address | Notes |
| --- | ---: | --- |
| `*TIMLP0400` | `0x463474`, `0x1138140` | Embedded TNS blobs |
| `*TIMLP0601` | `0x11436c0`, `0x153a2c0` | Embedded TNS blobs |
| `Document.xml` | Near embedded TNS local headers | No useful direct xrefs in flash IDB |
| `Problem1.xml` | Near embedded TNS local headers | No useful direct xrefs in flash IDB |

Installed desktop library anchors in `C:\Program Files\TI Education\TI-Nspire CX Student Software\lib\phoenix.dll`:

| String/constant | Evidence |
| --- | --- |
| `*TIMLP` | First local header magic handling |
| `TIPD` | TNS EOCD replacement |
| `Document.xml` | ZIP/TNS document handling |
| `zlib`, `compression`, `unknown compression method` | ZIP decompression path |
| `c:\Jenkins\workspace\nspire-pc\phoenix\zip\src\zipfile.c` | ZIP/TNS source path string |

## Candidate Functions

`phoenix.dll` static imagebase: `0x180000000`.

| Function | Evidence |
| ---: | --- |
| `0x180a91e90` | ZIP/TNS local header parser candidate. Compares `PK\x03\x04`, calls `0x180a92800` for `*TIMLP`, parses compression method. |
| `0x180a92009` | `cmp r15w, 0xd`; method 13 branch in local header parse path. |
| `0x180a953c0` | Normal zlib/inflate wrapper candidate. |
| `0x180a957d0` | Method 13 decode pipeline candidate. Initializes TIXC, initializes method 13 crypto, decrypts body, raw-inflates, expands TIXC. |
| `0x180cb15a0` | Method 13 crypto context init. |
| `0x180cb1340` | Decrypts/parses first 40-byte method 13 header. |
| `0x180cb06f0` | Decrypts method 13 body by XORing with 3DES-generated keystream. |
| `0x180a93a70` | TIXC context init. |
| `0x180a93d50` | TIXC token stream to XML expander. |

IDA renames applied:

| Address | Name |
| ---: | --- |
| `0x180a93a70` | `tixc_context_init_candidate` |
| `0x180a93d50` | `tixc_expand_candidate` |
| `0x180a94720` | `tixc_lookup_tag_candidate` |
| `0x180a94780` | `tixc_decode_text_token_candidate` |

## Phoenix TIXC Boundary

Previous Python backend:

```python
dll = ctypes.WinDLL(r"C:\Program Files\TI Education\TI-Nspire CX Student Software\lib\phoenix.dll")
base = dll._handle
init = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(base + 0xA93A70)
expand = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)(base + 0xA93D50)
```

Context layout inferred from `tixc_context_init_candidate` and the Python caller:

| Offset | Meaning |
| ---: | --- |
| `0x00` | input TIXC pointer |
| `0x08` | input bytes remaining |
| `0x10` | output pointer |
| `0x18` | output capacity remaining |
| `0x1c` | output bytes written |
| `0x28` | tag dictionary pointer table, 256 entries |
| `0x30` | attribute dictionary pointer table, 256 entries |
| `0x38` | tag dictionary string storage |
| `0x40` | attribute dictionary string storage |
| `0x48` | current token buffer |
| `0x50` | pending output buffer |
| `0x58` | tag dictionary count |
| `0x5c` | attribute dictionary count |
| `0x60` | current token length |
| `0x64` | main TIXC parser state |
| `0x68` | text decoder substate |

`tixc_expand_candidate(ctx)` returns `0` while it can continue, `1` when no input remains, and negative-style unsigned error values for malformed TIXC.

## Method 13 Algorithm

Input is the method 13 compressed payload from a TNS entry.

1. Decrypt the first 40 bytes with fixed-key 3DES ECB decrypt.
2. Validate decrypted header starts with `TIEN0100`.
3. Read little-endian block count at header offset `0x08`. Observed supported value: `0x400`.
4. Read little-endian counter seed at header offset `0x0c`.
5. Read 21 bytes of key material at header offset `0x10`.
6. Convert each 7-byte chunk into an 8-byte DES key with odd parity. Three chunks make a 24-byte 3DES key.
7. Body decrypt:
   - For each 8-byte encrypted block, build counter block `00 00 00 00 || little32(seed + block_index)`.
   - Encrypt the counter block with the derived 3DES key.
   - XOR keystream with ciphertext.
8. Raw deflate the decrypted body with `wbits=-15`.
9. The inflated stream starts with `TIXC0100` and is not final XML.
10. Expand TIXC to XML with `tixc_decode.py`. The former `phoenix.dll` static function `0x180a93d50` is now only a comparison backend.

## TIXC Algorithm

Implemented in `tixc_decode.py`.

TIXC is a tokenized XML stream:

1. Header begins `TIXC0100-<xml-version>?>`.
2. Decoder emits `<?xml version="<xml-version>" encoding="UTF-8" ?>`.
3. XML syntax bytes are mostly literal.
4. Element names are added to a 256-entry tag dictionary as they are first seen.
5. Attribute names are added to a 256-entry attribute dictionary as they are first seen.
6. Token byte `0x0c` starts a tag dictionary reference after `<`.
7. Token byte `0x0e` emits a close-tag form using the tag dictionary.
8. Token byte `0x0f` emits a space and switches to attribute dictionary lookup.
9. Text and attribute values are passed through `tixc_decode_text_token_candidate`, a compact byte/state decoder with two shorthand tables:

```text
 etaionsrhAlcduFmfpgybwvkxqjz,.'
0123456789AN,.EFx; (){}[]^+-/*PB
```

Special table symbols observed:

| Symbol | Output |
| --- | --- |
| `N` | UTF-8 minus sign `e2 88 92` |
| `E` | `ef 80 80` |
| `P` | `))` |
| `B` | `][` |
| `A` | reset/end sentinel |
| `F` | continuation sentinel |

CDATA is handled as a literal `<![CDATA[` state until `]]>`.

Fixed method 13 header key:

```text
79 c4 e0 f4 5e ef 7a 5b 70 13 7a 57 c2 fd 3d 2c c2 70 7c c1 ad 2f 15 75
```

Observed decrypted header for `zzcold888probe.tns` `Document.xml`:

```text
54 49 45 4e 30 31 30 30 00 04 00 00 9f 1c 20 af
8d 24 ef 91 1c 6e b6 27 02 b5 38 e0 4b 13 e0 e9
d4 e0 3d 75 16 00 00 00
```

## Implemented Files

- `tns_outer_parse.py`
  - Parses modified ZIP/TNS containers.
  - Handles first local header `*TIMLP####`.
  - Handles `TIPD` EOCD.
  - Lists entries and extracts raw payloads.
- `tns_method13.py`
  - Implements method 13 header decrypt, body decrypt, and raw deflate.
  - Provides `PureTixcExpander` for final TIXC expansion.
  - Keeps `PhoenixTixcExpander` for comparison only.
- `tixc_decode.py`
  - Pure Python `TIXC0100` to XML decoder.
- `tixc_encode.py`
  - Pure Python XML to `TIXC0100` encoder.
  - Emits conservative literal attributes for compatibility with `phoenix.dll`.
- `tns_to_xml.py`
  - Compatibility wrapper for the decode half of `tnstools.py`.
- `tnstools.py`
  - Main command-line tool.
  - Decodes `.tns` files to `<input filename>.xml` folders.
  - Builds `.tns` files independently from raw XML using XML -> TIXC -> method 13.
  - Supports `--allow-stored-xml` for the old experimental method 0 stored XML writer.
  - Supports verification by decoding the rebuilt file and comparing XML bytes.
  - Supports `--validate`, which scans a validation folder and performs temporary decode/rebuild/redecode XML-equivalence tests.
  - Supports `--validate-phoenix`, which also expands rebuilt TIXC through `phoenix.dll` and compares XML bytes.

## Validation

Commands run:

```powershell
python tns_outer_parse.py C:\Users\Administrator\Downloads\zzcold888probe.tns
python tns_to_xml.py C:\Users\Administrator\Downloads\zzcold888probe.tns out_xml_zzcold --list
python tns_to_xml.py zzudftest.tns out_xml_zzudftest_pure --list --tixc-backend pure
python tns_to_xml.py zzudftest.tns out_xml_zzudftest_default --list
python tns_to_xml.py "C:\Program Files\TI Education\TI-Nspire CX Student Software\res\documents\MyLib\linalg.tns" out_xml_linalg --list
python tns_to_xml.py "C:\Program Files\TI Education\TI-Nspire CX Student Software\res\documents\MyLib\linalg.tns" out_xml_linalg_pure --list --tixc-backend pure
python tnstools.py -tns zzudftest.tns --list
python tnstools.py -tns zzudftest.tns -out zzudftest_cli_xml --artifacts --list
python tnstools.py -xml zzudftest_cli_xml -out rebuilt_zzudftest_store.tns --list --verify
python tnstools.py -xml calculus.tns.xml -out rebuilt_calculus_store.tns --list --verify
python tnstools.py --validate validation_temp_test
python tnstools.py -xml zz_xml_for_encode -out encoded_zz2.tns --verify --list
python tnstools.py -tns encoded_zz2.tns -out encoded_zz2_phoenix_xml --tixc-backend phoenix
python tnstools.py -xml calculus.tns.xml -out encoded_calculus2.tns --verify --list
python tnstools.py -tns encoded_calculus2.tns -out encoded_calculus2_phoenix_xml --tixc-backend phoenix
python -m py_compile tixc_encode.py tnstools.py tixc_decode.py tns_outer_parse.py tns_method13.py tns_to_xml.py
python tnstools.py --validate validation_batch --validate-phoenix
```

`zzcold888probe.tns`:

| Entry | Method | Compressed | Uncompressed | Result |
| --- | ---: | ---: | ---: | --- |
| `Document.xml` | 13 | 446 | 957 | XML written, size ok, CRC ok |
| `Problem1.xml` | 13 | 1041 | 4578 | XML written, size ok, CRC ok |

Markers found in decoded `Problem1.xml`:

- `<prob`
- `pe:data`
- `pe:editor`
- `r2dtotree`
- `Define LibPub`
- `LibPub`

Installed `linalg.tns`:

| Entry | Method | Compressed | Uncompressed | Result |
| --- | ---: | ---: | ---: | --- |
| `Document.xml` | 13 | 283 | 572 | XML written, size ok, CRC ok |
| `Problem1.xml` | 13 | 8021 | 26858 | XML written, size ok, CRC ok |

`zzudftest.tns` with pure TIXC:

| Entry | Method | Compressed | Uncompressed | Result |
| --- | ---: | ---: | ---: | --- |
| `Document.xml` | 13 | 446 | 957 | XML written, size ok, CRC ok |
| `Problem1.xml` | 13 | 1041 | 4578 | XML written, size ok, CRC ok |

Markers found in pure-decoded `zzudftest` `Problem1.xml`:

- `zztestadd`
- `a,b`
- `Return a+b`
- `Define LibPub`
- `LibPub`
- `pe:data`
- `pe:editor`
- `pe:laststoredexpr`
- `r2dtotree`
- `zztestadd(3,2)`
- `<sp:disp>5</sp:disp>`

External user validation:

- A randomly sourced CX-era `.tns` decoded successfully with the pure Python pipeline.
- Decoded output contained a `TI.ScriptApp` widget with `sc:md`, `sc:mde`, `sc:script`, custom menu definitions, and a large Lua CDATA body.
- The file predates the CX II environment used for `phoenix.dll` comparison, so this is positive compatibility evidence across older CX-origin documents and newer CX II-era decoder code.
- The app content itself is copyrighted and was not added to this repository.

XML-to-TNS rebuild validation:

| Source XML folder | Rebuilt file | Result |
| --- | --- | --- |
| `zz_xml_for_encode` | `encoded_zz2.tns` | method 13 encoded, pure decode-verify ok, phoenix decode ok |
| `calculus.tns.xml` | `encoded_calculus2.tns` | method 13 encoded, pure decode-verify ok, phoenix decode ok |

Size/hash examples:

| File | MD5 | Size |
| --- | --- | ---: |
| `zzudftest.tns` | `483c47f23a72c5e4c62aa004ff407628` | 1715 |
| `encoded_zz2.tns` | `726509125990510ad466e789573a33d7` | 1624 |
| `encoded_calculus2.tns` | `e1e64457dd4973651c370bbce7d37210` | 13966 |

Different checksums are expected for independent re-encoding. The validation
target is decoded XML identity and acceptance by the TIXC expander.

`--validate` result on `zzudftest.tns`:

- original decode: ok
- temporary rebuild: ok
- rebuilt decode: ok
- XML comparison: byte-for-byte identical
- TNS binary comparison: differs, expected for independent re-encoding
- overall result: pass

Phoenix compatibility result:

- Initial generated TIXC using attribute dictionary references was accepted by the pure decoder but truncated by `phoenix.dll` at the first repeated attribute reference.
- Encoder was changed to emit attributes literally instead of using the `0x0f` attribute-reference token.
- After that change, `encoded_zz2.tns` and `encoded_calculus2.tns` decode with phoenix to byte-identical XML.
- Added conservative text-token optimization in `tixc_encode.py`:
  - uses safe common-letter shorthand runs from the TIXC eta table;
  - uses safe numeric shorthand runs from the TIXC digit table;
  - avoids sentinel-conflicting table symbols;
  - keeps the encoder's internal `decode_tixc(encode_tixc(xml)) == xml` guard.

`large.tns` validation:

- Content coverage: Lists & Spreadsheet/tabulator XML, Scratchpad/calculator XML, and DataGrapher graph XML.
- Original decode: `Document.xml` 1174 bytes, `Problem1.xml` 24626 bytes, CRC/size ok.
- Initial encode failed the internal TIXC roundtrip check around repeated no-attribute tags such as `<n>b</n>`.
- Root cause: TIXC tag dictionary start references (`0x0c index`) have an implicit `>` when the next byte is content. The encoder was incorrectly emitting an explicit `>` for repeated tags with no attributes.
- Fix: omit explicit `>` only for bare repeated start tags; still emit `>` for first-use tags and repeated tags with attributes.
- Rebuilt `encoded_large.tns`: method 13 entries, size 3748 bytes vs original 3926 bytes.
- Pure decoder verification: XML byte-for-byte identical, CRC/size ok.
- Phoenix verification: `encoded_large.tns` decodes to byte-identical `Document.xml` and `Problem1.xml`.
- `python tnstools.py --validate validation_temp_large`: pass.

Additional batch validation:

| Input | Original size | Rebuilt size | Coverage | Result |
| --- | ---: | ---: | --- | --- |
| `2048.tns` | 4598 | 4480 | game/program-style document | pure validate pass, phoenix XML compare pass |
| `Mazes3D.tns` | 4366 | 3619 | game/program-style document | pure validate pass, phoenix XML compare pass |
| `large.tns` | 3926 | 3857 | Lists & Spreadsheet, Calculator, DataGrapher | pure validate pass, phoenix XML compare pass |
| `zzudftest.tns` | 1715 | temporary | Program Editor UDF, Scratchpad | pure validate pass, phoenix XML compare pass |

`--validate-phoenix` note:

- A copied local `phoenix.dll` may fail to load if its dependencies are absent.
- The default installed Student Software path works when Student Software is installed.

Embedded flash samples:

- Document entries decode correctly.
- Larger Problem entries extracted from embedded flash blobs fail during raw deflate in both the Python decryptor and direct `phoenix.dll` crypto oracle. This is currently treated as an extraction/sample issue or a distinct embedded-resource variant, not as a failure of normal `.tns` file decoding.

## Unresolved Questions

- Validate against `summermaks.tns` once the file is available locally.
- Investigate embedded flash Problem entries that fail raw deflate after method 13 body decrypt.
- Roundtrip through Luna has not been attempted yet because the primary `summermaks.tns` file is absent.
- Actual Student Software open/save acceptance of the newly generated method 13 files still needs a GUI test.

## Current Limitation

The decoder is now standalone for the tested `TIXC0100` files. Remaining risk is untested TIXC variants or versions; keep `phoenix.dll` comparison available until more documents are covered.
