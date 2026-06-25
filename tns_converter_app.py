#!/usr/bin/env python3
"""
TNS Converter App — Single-file web application for TI-Nspire file conversion.

Combines: tixc_decode, tixc_encode, tns_outer_parse, tns_method13,
          tns_converter, and app (web server + HTML UI).

Usage:
    python3 tns_converter_app.py

Opens automatically http://localhost:8051 in your browser.
"""

from __future__ import annotations

import base64
import binascii
import csv
import dataclasses
import http.server
import io
import json
import pathlib
import re
import socketserver
import struct
import threading
import time
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
import zlib
from typing import Iterable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class _DES3Compat:
    MODE_ECB = "ecb"

    def __init__(self, key, mode):
        self._cipher = Cipher(algorithms.TripleDES(key), modes.ECB())

    @staticmethod
    def new(key, mode):
        return _DES3Compat(key, mode)

    def encrypt(self, data):
        enc = self._cipher.encryptor()
        return enc.update(data) + enc.finalize()

    def decrypt(self, data):
        dec = self._cipher.decryptor()
        return dec.update(data) + dec.finalize()


DES3 = _DES3Compat


# ===========================================================================
# tixc_decode.py — Pure Python decoder for TI-Nspire TIXC0100 XML token streams
# ===========================================================================

class TixcDecodeError(RuntimeError):
    pass


_TAG_NAME_TERMINATORS = {0x0E, 0x0F, 0x20, 0x2F, 0x3E}
_ETA_TABLE = b" etaionsrhAlcduFmfpgybwvkxqjz,.'"
_DIGIT_TABLE = b"0123456789AN,.EFx; (){}[]^+-/*PB"
_CDATA_OPEN = b"<![CDATA["
_CDATA_CLOSE = b"]]>"


def _special_digit(byte: int) -> bytes:
    if byte == ord("N"):
        return b"\xe2\x88\x92"
    if byte == ord("E"):
        return b"\xef\x80\x80"
    if byte == ord("P"):
        return b"))"
    if byte == ord("B"):
        return b"]["
    return bytes([byte])


class _TextDecoder:
    def __init__(self) -> None:
        self.state = 0
        self.count = 0
        self.tmp = 0

    def reset(self) -> None:
        self.state = 0
        self.count = 0
        self.tmp = 0

    def decode_byte(self, byte: int) -> bytes:
        out = bytearray()
        state = self.state

        if state == 0:
            if byte < 0xA0:
                needs_utf = (byte <= 0x1F and ((-9729 & 0xFFFFFFFF) >> byte) & 1) or byte >= 0x7F
                if needs_utf:
                    if (byte & 0xF0) == 0x80:
                        self.count = (byte & 0x0F) + 1
                        self.state = 28
                        return b""
                    if byte >= 8:
                        if byte == 8:
                            self.state = 30
                            return b""
                        if byte == 11:
                            self.state = 33
                            return b""
                        raise TixcDecodeError(f"unsupported TIXC text control byte 0x{byte:02x}")
                    self.tmp = (((byte & 7) | 0xF0) << 2) & 0xFF
                    self.count = 1
                    self.state = 27
                    return b""
                return bytes([byte])

            if (byte & 0xF0) == 0xA0:
                ch = _ETA_TABLE[byte & 0x0F]
                if ch == ord("F"):
                    self.state = 24
                    return b""
                if ch == ord("A"):
                    self.state = 0
                    return b""
                self.state = 23
                return bytes([ch])

            if (byte & 0xF0) == 0xF0:
                ch = _DIGIT_TABLE[byte & 0x0F]
                if ch == ord("A"):
                    self.state = 26
                    return b""
                if ch == ord("F"):
                    self.state = 0
                    return b""
                self.state = 25
                return _special_digit(ch)
            return b""

        if state == 23:
            ch1 = _ETA_TABLE[byte >> 4]
            if ch1 == ord("F"):
                return bytes([_ETA_TABLE[(byte & 0x0F) + 16]])
            if ch1 == ord("A"):
                self.state = 0
                return b""
            out.append(ch1)
            ch2 = _ETA_TABLE[byte & 0x0F]
            if ch2 == ord("F"):
                self.state = 24
                return bytes(out)
            if ch2 == ord("A"):
                self.state = 0
                return bytes(out)
            out.append(ch2)
            return bytes(out)

        if state == 24:
            out.append(_ETA_TABLE[(byte >> 4) + 16])
            ch2 = _ETA_TABLE[byte & 0x0F]
            if ch2 == ord("F"):
                return bytes(out)
            if ch2 == ord("A"):
                self.state = 0
                return bytes(out)
            out.append(ch2)
            self.state = 23
            return bytes(out)

        if state == 25:
            ch1 = _DIGIT_TABLE[byte >> 4]
            if ch1 == ord("A"):
                ch2 = _DIGIT_TABLE[(byte & 0x0F) + 16]
                if ch2 == ord("P"):
                    return b"))"
                if ch2 == ord("B"):
                    return b"]["
                return _special_digit(ch2)
            if ch1 == ord("F"):
                self.state = 0
                return b""
            out += _special_digit(ch1)
            ch2 = _DIGIT_TABLE[byte & 0x0F]
            if ch2 == ord("A"):
                self.state = 26
                return bytes(out)
            if ch2 == ord("F"):
                self.state = 0
                return bytes(out)
            out += _special_digit(ch2)
            return bytes(out)

        if state == 26:
            ch1 = _DIGIT_TABLE[(byte >> 4) + 16]
            if ch1 == ord("P"):
                out += b"))"
            elif ch1 == ord("B"):
                out += b"]["
            else:
                out += _special_digit(ch1)
            ch2 = _DIGIT_TABLE[byte & 0x0F]
            if ch2 == ord("A"):
                return bytes(out)
            if ch2 == ord("F"):
                self.state = 0
                return bytes(out)
            self.state = 25
            out += _special_digit(ch2)
            return bytes(out)

        if state == 27:
            self.state = 0
            self.count = 0
            return bytes([(self.tmp | (byte >> 6)) & 0xFF, (byte & 0x3F) | 0x80])

        if state == 28:
            self.state = 29
            self.tmp = byte
            return bytes([(byte >> 4) | 0xE0])

        if state == 29:
            self.count -= 1
            if self.count <= 0:
                self.state = 0
            else:
                self.state = 28
            return bytes([((byte >> 6) | (((self.tmp & 0x0F) | 0xE0) << 2)) & 0xFF, (byte & 0x3F) | 0x80])

        if state == 30:
            self.tmp = byte
            self.state = 31
            if byte >= 0x20:
                self.count = 2
                return bytes([0xF8, (byte >> 2) | 0x80])
            self.count = 1
            return bytes([((byte >> 2) & 7) | 0xF0])

        if state in (31, 35):
            self.count = 1
            self.state = 32
            out = bytes([((byte >> 4) | (((self.tmp & 3) | 0xF8) << 4)) & 0xFF])
            self.tmp = byte
            return out

        if state in (32, 36):
            self.state = 0
            self.count = 0
            return bytes([((byte >> 6) | (((self.tmp & 0x0F) | 0xE0) << 2)) & 0xFF, (byte & 0x3F) | 0x80])

        if state == 33:
            self.state = 34
            if byte >= 4:
                return bytes([(((byte & 0x40) != 0) | 0xFC) & 0xFF, (byte & 0x3F) | 0x80])
            return bytes([(byte & 3) | 0xF8])

        if state == 34:
            self.state = 35
            self.tmp = byte
            self.count = 1
            return bytes([(byte >> 2) | 0x80])

        raise TixcDecodeError(f"unsupported TIXC text state {state}")


def decode_tixc(data: bytes) -> bytes:
    """Convert TIXC0100 stream bytes to readable XML bytes."""
    if not data.startswith(b"TIXC"):
        raise TixcDecodeError("TIXC stream does not start with TIXC")

    dash = data.find(b"-", 4)
    qmark = data.find(b"?", dash + 1)
    if dash < 0 or qmark < 0 or data[qmark : qmark + 2] != b"?>":
        raise TixcDecodeError("invalid TIXC header")
    version = data[dash + 1 : qmark]

    pos = qmark + 2
    out = bytearray(b'<?xml version="' + version + b'" encoding="UTF-8" ?>')
    tag_dict: list[bytes] = []
    attr_dict: list[bytes] = []
    token = bytearray()
    text = _TextDecoder()
    state = 1
    cdata_match = 0

    def read_byte() -> int:
        if pos >= len(data):
            raise TixcDecodeError("unexpected end of TIXC stream")
        return data[pos]

    while pos < len(data):
        b = read_byte()

        if state == 1:
            if b != ord("<"):
                raise TixcDecodeError("expected root '<' after TIXC header")
            out.append(b)
            pos += 1
            state = 2

        elif state == 2:
            if b in _TAG_NAME_TERMINATORS:
                if b == 0x0E:
                    out += b"></"
                    state = 12
                elif b == 0x0F:
                    out.append(0x20)
                    state = 13
                elif b == 0x20:
                    if not token:
                        raise TixcDecodeError("empty tag before attribute separator")
                    out.append(0x20)
                    state = 4
                elif b == 0x2F:
                    out.append(0x2F)
                    state = 10 if not token else 9
                elif b == 0x3E:
                    if not token:
                        raise TixcDecodeError("empty tag before '>'")
                    out.append(0x3E)
                    state = 3
                if token:
                    if len(tag_dict) < 256:
                        tag_dict.append(bytes(token))
                    token.clear()
                pos += 1
            else:
                if len(token) >= 64:
                    raise TixcDecodeError("tag token exceeds 64 bytes")
                token.append(b)
                out.append(b)
                pos += 1

        elif state == 3:
            text.reset()
            if b == ord("<"):
                out.append(b)
                pos += 1
                token.clear()
                state = 17
            elif b == 0x0C:
                out.append(ord("<"))
                pos += 1
                token.clear()
                state = 11
            elif b == 0x0E:
                out += b"</"
                pos += 1
                token.clear()
                state = 12
            else:
                token.clear()
                state = 8

        elif state == 4:
            if b == ord("="):
                if len(attr_dict) < 256:
                    attr_dict.append(bytes(token))
                token.clear()
                out.append(b)
                pos += 1
                state = 5
            else:
                token.append(b)
                out.append(b)
                pos += 1

        elif state == 5:
            pos += 1
            if b == ord('"'):
                out.append(b)
                state = 6
            elif b != 0x20:
                raise TixcDecodeError("expected quote or space after attribute '='")

        elif state == 6:
            if b == ord('"') and text.state == 0:
                out.append(b)
                pos += 1
                token.clear()
                state = 7
            else:
                out += text.decode_byte(b)
                pos += 1

        elif state == 7:
            if b == ord(">"):
                out.append(b)
                pos += 1
                state = 3
            elif b == ord("/"):
                out.append(b)
                pos += 1
                state = 10
            elif b == 0x20:
                out.append(b)
                pos += 1
                state = 4
            elif b == 0x0F:
                out.append(0x20)
                pos += 1
                state = 13
            else:
                raise TixcDecodeError(f"unexpected byte 0x{b:02x} after attribute value")

        elif state == 8:
            if b == ord("<") and text.state == 0:
                out.append(b)
                pos += 1
                token.clear()
                state = 2
            elif b == 0x0C and text.state == 0:
                out.append(ord("<"))
                pos += 1
                token.clear()
                state = 11
            elif b == 0x0E and text.state == 0:
                out += b"</"
                pos += 1
                token.clear()
                state = 12
            else:
                out += text.decode_byte(b)
                pos += 1

        elif state == 9:
            out.append(b)
            pos += 1
            if b == ord(">"):
                state = 3

        elif state == 10:
            if b != ord(">"):
                raise TixcDecodeError("expected '>' after '/'")
            out.append(b)
            pos += 1
            state = 3

        elif state == 11:
            if b >= len(tag_dict):
                raise TixcDecodeError(f"tag dictionary index {b} out of range")
            tag = tag_dict[b]
            out += tag
            pos += 1
            state = 14

        elif state == 12:
            if b >= len(tag_dict):
                raise TixcDecodeError(f"tag dictionary index {b} out of range")
            tag = tag_dict[b]
            out += tag + b">"
            pos += 1
            state = 3

        elif state == 13:
            if b >= len(attr_dict):
                raise TixcDecodeError(f"attribute dictionary index {b} out of range")
            out += attr_dict[b] + b'="'
            pos += 1
            text.reset()
            state = 6

        elif state == 14:
            if b == 0x20:
                out.append(0x20)
                pos += 1
                state = 4
            elif b == ord("/"):
                pos += 1
                state = 15
            elif b == 0x0F:
                out.append(0x20)
                pos += 1
                state = 13
            else:
                out.append(ord(">"))
                state = 3

        elif state == 15:
            if b == ord(">"):
                out.append(ord("/"))
                state = 10
            else:
                out.append(ord(">"))
                state = 3

        elif state == 17:
            if b == ord("!"):
                out.append(b)
                pos += 1
                cdata_match = 2
                state = 18
            else:
                state = 2

        elif state == 18:
            if cdata_match >= len(_CDATA_OPEN):
                state = 19
                token.clear()
                continue
            if b != _CDATA_OPEN[cdata_match]:
                raise TixcDecodeError("invalid CDATA opener")
            out.append(b)
            pos += 1
            cdata_match += 1

        elif state == 19:
            out.append(b)
            pos += 1
            if b == ord("]"):
                cdata_match = 1
                state = 20

        elif state == 20:
            out.append(b)
            pos += 1
            if cdata_match < len(_CDATA_CLOSE) and b == _CDATA_CLOSE[cdata_match]:
                cdata_match += 1
            else:
                state = 19
                cdata_match = 0
            if cdata_match == len(_CDATA_CLOSE):
                state = 3
                cdata_match = 0

        else:
            raise TixcDecodeError(f"unsupported TIXC parser state {state}")

    if state not in (3,):
        raise TixcDecodeError(f"TIXC stream ended in state {state}")
    return bytes(out)


# ===========================================================================
# tixc_encode.py — Minimal pure Python encoder for TIXC0100 XML token streams
# ===========================================================================

class TixcEncodeError(RuntimeError):
    pass


XML_DECL_RE = re.compile(br'^<\?xml\s+version="([^"]+)"\s+encoding="UTF-8"\s+\?>')
_ETA_TABLE_ENC = b" etaionsrhAlcduFmfpgybwvkxqjz,.'"
_DIGIT_TABLE_ENC = b"0123456789AN,.EFx; (){}[]^+-/*PB"
_ETA_SAFE = {c: i for i, c in enumerate(_ETA_TABLE_ENC[:15]) if c != ord("A")}
_DIGIT_SAFE = {c: i for i, c in enumerate(_DIGIT_TABLE_ENC[:14]) if c not in (ord("A"), ord("N"))}
_MIN_TOKEN_RUN = 6


def _encode_utf8_sequence(seq: bytes) -> bytes:
    if len(seq) == 2:
        a, b = seq
        if not (0xC0 <= a <= 0xDF and 0x80 <= b <= 0xBF):
            raise TixcEncodeError(f"invalid two-byte UTF-8 sequence: {seq!r}")
        control = (a & 0x1C) >> 2
        packed = ((a & 0x03) << 6) | (b & 0x3F)
        return bytes([control, packed])

    if len(seq) == 3:
        a, b, c = seq
        if not (0xE0 <= a <= 0xEF and 0x80 <= b <= 0xBF and 0x80 <= c <= 0xBF):
            raise TixcEncodeError(f"invalid three-byte UTF-8 sequence: {seq!r}")
        x = ((a & 0x0F) << 4) | ((b & 0x3C) >> 2)
        y = ((b & 0x03) << 6) | (c & 0x3F)
        return bytes([0x80, x, y])

    if len(seq) == 4:
        a, b, c, d = seq
        if not (0xF0 <= a <= 0xF7 and 0x80 <= b <= 0xBF and 0x80 <= c <= 0xBF and 0x80 <= d <= 0xBF):
            raise TixcEncodeError(f"invalid four-byte UTF-8 sequence: {seq!r}")
        x = ((a & 0x07) << 2) | ((b & 0x30) >> 4)
        y = ((b & 0x0F) << 4) | ((c & 0x3C) >> 2)
        z = ((c & 0x03) << 6) | (d & 0x3F)
        return bytes([0x08, x, y, z])

    raise TixcEncodeError(f"unsupported UTF-8 sequence length: {len(seq)}")


def _pack_table_run(prefix: int, terminator: int, indexes: list[int]) -> bytes:
    # Text tokens pack the first table index into the low nibble of the control
    # byte, then two indexes per byte until a table-specific terminator nibble.
    if not indexes:
        return b""
    out = bytearray([prefix | indexes[0]])
    rest = indexes[1:]
    i = 0
    while i + 1 < len(rest):
        out.append((rest[i] << 4) | rest[i + 1])
        i += 2
    if i < len(rest):
        out.append((rest[i] << 4) | terminator)
    else:
        out.append(terminator << 4)
    return bytes(out)


def _table_run(data: bytes, start: int, table: dict[int, int]) -> tuple[int, list[int]]:
    indexes: list[int] = []
    pos = start
    while pos < len(data):
        idx = table.get(data[pos])
        if idx is None:
            break
        indexes.append(idx)
        pos += 1
    return pos, indexes


def _encode_text(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b < 0x80:
            # Only use shorthand tables for long safe runs. Literal ASCII is
            # more compatible for short/mixed text and easier to debug.
            digit_end, digit_indexes = _table_run(data, i, _DIGIT_SAFE)
            eta_end, eta_indexes = _table_run(data, i, _ETA_SAFE)
            if len(digit_indexes) >= _MIN_TOKEN_RUN and len(digit_indexes) >= len(eta_indexes):
                out += _pack_table_run(0xF0, 0x0F, digit_indexes)
                i = digit_end
                continue
            if len(eta_indexes) >= _MIN_TOKEN_RUN:
                out += _pack_table_run(0xA0, 0x0A, eta_indexes)
                i = eta_end
                continue
            if b in (0x09, 0x0A, 0x0D) or 0x20 <= b <= 0x7E:
                out.append(b)
                i += 1
                continue
            raise TixcEncodeError(f"unsupported XML text control byte 0x{b:02x}")

        if 0xC0 <= b <= 0xDF:
            size = 2
        elif 0xE0 <= b <= 0xEF:
            size = 3
        elif 0xF0 <= b <= 0xF7:
            size = 4
        else:
            raise TixcEncodeError(f"invalid UTF-8 lead byte 0x{b:02x}")
        seq = data[i : i + size]
        if len(seq) != size:
            raise TixcEncodeError("truncated UTF-8 sequence")
        out += _encode_utf8_sequence(seq)
        i += size
    return bytes(out)


def _name_end(data: bytes, pos: int) -> int:
    while pos < len(data) and data[pos] not in b" \t\r\n/=>":
        pos += 1
    return pos


def _skip_ws(data: bytes, pos: int) -> int:
    while pos < len(data) and data[pos] in b" \t\r\n":
        pos += 1
    return pos


def encode_tixc(xml: bytes) -> bytes:
    """Encode readable XML bytes as a TIXC0100 stream.

    The encoder intentionally emits a simple stream: literal first-use tag and
    attribute names, dictionary references for repeats and close tags, and text
    bytes encoded only where TIXC requires it.
    """
    match = XML_DECL_RE.match(xml)
    if not match:
        raise TixcEncodeError("XML must start with a UTF-8 declaration")
    version = match.group(1)
    body = xml[match.end() :]

    out = bytearray(b"TIXC0100-" + version + b"?>")
    tag_dict: list[bytes] = []
    tag_index: dict[bytes, int] = {}

    i = 0
    while i < len(body):
        if body.startswith(b"<![CDATA[", i):
            end = body.find(b"]]>", i + 9)
            if end < 0:
                raise TixcEncodeError("unterminated CDATA section")
            out += body[i : end + 3]
            i = end + 3
            continue

        if body[i] != ord("<"):
            next_tag = body.find(b"<", i)
            if next_tag < 0:
                next_tag = len(body)
            out += _encode_text(body[i:next_tag])
            i = next_tag
            continue

        if body.startswith(b"</", i):
            end = body.find(b">", i + 2)
            if end < 0:
                raise TixcEncodeError("unterminated close tag")
            name = body[i + 2 : end]
            idx = tag_index.get(name)
            if idx is None:
                raise TixcEncodeError(f"close tag has no dictionary entry: {name!r}")
            out += bytes([0x0E, idx])
            i = end + 1
            continue

        if body.startswith(b"<?", i):
            raise TixcEncodeError("processing instructions are only supported in the XML declaration")
        if body.startswith(b"<!", i):
            raise TixcEncodeError("only CDATA markup is supported")

        pos = i + 1
        name_end_pos = _name_end(body, pos)
        if name_end_pos == pos:
            raise TixcEncodeError(f"empty tag name at offset {i}")
        name = body[pos:name_end_pos]
        idx = tag_index.get(name)
        used_tag_ref = idx is not None
        if idx is None:
            if len(tag_dict) >= 256:
                raise TixcEncodeError("tag dictionary exhausted")
            idx = len(tag_dict)
            tag_dict.append(name)
            tag_index[name] = idx
            out += b"<" + name
        else:
            out += bytes([0x0C, idx])

        pos = name_end_pos
        has_attrs = False
        while True:
            pos = _skip_ws(body, pos)
            if pos >= len(body):
                raise TixcEncodeError("unterminated start tag")
            if body.startswith(b"/>", pos):
                out += b"/>"
                i = pos + 2
                break
            if body[pos] == ord(">"):
                # A tag dictionary start reference has an implicit '>' when it
                # is followed directly by content. If attributes were emitted,
                # the decoder is in the "after attribute value" state and needs
                # an explicit '>' to enter content state.
                if not used_tag_ref or has_attrs:
                    out.append(ord(">"))
                i = pos + 1
                break

            attr_start = pos
            attr_end = _name_end(body, pos)
            attr = body[attr_start:attr_end]
            pos = _skip_ws(body, attr_end)
            if pos >= len(body) or body[pos] != ord("="):
                raise TixcEncodeError(f"expected '=' after attribute {attr!r}")
            pos = _skip_ws(body, pos + 1)
            if pos >= len(body) or body[pos] != ord('"'):
                raise TixcEncodeError(f"expected double quote for attribute {attr!r}")
            value_start = pos + 1
            value_end = body.find(b'"', value_start)
            if value_end < 0:
                raise TixcEncodeError(f"unterminated value for attribute {attr!r}")
            value = body[value_start:value_end]
            has_attrs = True

            out += b" " + attr + b'="' + _encode_text(value) + b'"'
            pos = value_end + 1

    encoded = bytes(out)
    decoded = decode_tixc(encoded)
    if decoded != xml:
        first = next((i for i, (a, b) in enumerate(zip(decoded, xml)) if a != b), min(len(decoded), len(xml)))
        got = decoded[max(0, first - 80) : first + 160]
        want = xml[max(0, first - 80) : first + 160]
        raise TixcEncodeError(
            "internal TIXC roundtrip check failed at byte "
            f"{first}: got {got!r}; expected {want!r}"
        )
    return encoded


# ===========================================================================
# tns_outer_parse.py — Parse the outer TI-Nspire .tns container
# ===========================================================================

LOCAL_SIG = b"PK\x03\x04"
CD_SIG = b"PK\x01\x02"
EOCD_SIG = b"PK\x05\x06"
TIPD_SIG = b"TIPD"
TIMLP_PREFIX = b"*TIMLP"


@dataclasses.dataclass
class TnsEntry:
    name: str
    method: int
    crc32: int
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int
    data_offset: int
    name_len: int
    extra_len: int
    flags: int = 0
    source: str = "central"

    @property
    def data_end(self) -> int:
        return self.data_offset + self.compressed_size


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _decode_name(raw: bytes) -> str:
    for enc in ("utf-8", "cp437", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1", errors="replace")


def _find_eocd(data: bytes) -> tuple[int, bytes] | None:
    best: tuple[int, bytes] | None = None
    for sig in (EOCD_SIG, TIPD_SIG):
        off = data.rfind(sig)
        if off >= 0 and off + 22 <= len(data):
            if best is None or off > best[0]:
                best = (off, sig)
    return best


def _parse_local_at(data: bytes, off: int) -> tuple[int, int, int, int, int, int, int, str] | None:
    """Return method, flags, crc, csize, usize, nlen, xlen, kind."""
    if data.startswith(LOCAL_SIG, off):
        base = off + 4
        kind = "pk"
    elif data.startswith(TIMLP_PREFIX, off) and off + 10 <= len(data):
        base = off + 10
        kind = data[off : off + 10].decode("ascii", errors="replace")
    else:
        return None
    if base + 26 > len(data):
        return None
    flags = _u16(data, base + 2)
    method = _u16(data, base + 4)
    crc32 = _u32(data, base + 10)
    csize = _u32(data, base + 14)
    usize = _u32(data, base + 18)
    nlen = _u16(data, base + 22)
    xlen = _u16(data, base + 24)
    return method, flags, crc32, csize, usize, nlen, xlen, kind


def _local_data_offset(data: bytes, off: int, nlen: int, xlen: int) -> int:
    if data.startswith(LOCAL_SIG, off):
        return off + 30 + nlen + xlen
    if data.startswith(TIMLP_PREFIX, off):
        return off + 36 + nlen + xlen
    raise ValueError(f"not a local header at 0x{off:x}")


def _candidate_local_offsets(raw_off: int) -> Iterable[int]:
    yield raw_off
    yield raw_off + 6
    if raw_off >= 6:
        yield raw_off - 6


def _parse_central_directory(data: bytes) -> list[TnsEntry]:
    eocd = _find_eocd(data)
    if not eocd:
        return []
    eocd_off, _sig = eocd
    total_entries = _u16(data, eocd_off + 10)
    cd_size = _u32(data, eocd_off + 12)
    cd_off = _u32(data, eocd_off + 16)

    starts = [cd_off]
    if cd_off >= 6:
        starts.append(cd_off - 6)
    starts.append(cd_off + 6)
    starts.append(data.find(CD_SIG))

    for start in starts:
        if start < 0 or start + 46 > len(data) or not data.startswith(CD_SIG, start):
            continue
        entries: list[TnsEntry] = []
        off = start
        ok = True
        limit = min(len(data), start + cd_size + 1024)
        for _ in range(total_entries or 10_000):
            if off + 46 > len(data) or not data.startswith(CD_SIG, off):
                ok = total_entries == 0 or len(entries) == total_entries
                break
            flags = _u16(data, off + 8)
            method = _u16(data, off + 10)
            crc32 = _u32(data, off + 16)
            csize = _u32(data, off + 20)
            usize = _u32(data, off + 24)
            nlen = _u16(data, off + 28)
            xlen = _u16(data, off + 30)
            clen = _u16(data, off + 32)
            local_off = _u32(data, off + 42)
            name_raw = data[off + 46 : off + 46 + nlen]
            name = _decode_name(name_raw)

            local = None
            actual_local_off = local_off
            for cand in _candidate_local_offsets(local_off):
                local = _parse_local_at(data, cand)
                if local:
                    actual_local_off = cand
                    break
            if not local:
                ok = False
                break
            l_method, l_flags, l_crc32, l_csize, l_usize, l_nlen, l_xlen, _kind = local
            data_off = _local_data_offset(data, actual_local_off, l_nlen, l_xlen)
            entries.append(
                TnsEntry(
                    name=name,
                    method=method if method else l_method,
                    crc32=crc32 if crc32 else l_crc32,
                    compressed_size=csize if csize else l_csize,
                    uncompressed_size=usize if usize else l_usize,
                    local_header_offset=actual_local_off,
                    data_offset=data_off,
                    name_len=l_nlen,
                    extra_len=l_xlen,
                    flags=flags if flags else l_flags,
                    source="central",
                )
            )
            off += 46 + nlen + xlen + clen
            if total_entries == 0 and off >= limit:
                break
        if ok and entries:
            return entries
    return []


def _scan_local_headers(data: bytes) -> list[TnsEntry]:
    starts: list[int] = []
    if data.startswith(TIMLP_PREFIX):
        starts.append(0)
    off = 0
    while True:
        off = data.find(LOCAL_SIG, off)
        if off < 0:
            break
        starts.append(off)
        off += 1

    entries: list[TnsEntry] = []
    for off in sorted(set(starts)):
        parsed = _parse_local_at(data, off)
        if not parsed:
            continue
        method, flags, crc32, csize, usize, nlen, xlen, _kind = parsed
        data_off = _local_data_offset(data, off, nlen, xlen)
        name_start = data_off - nlen - xlen
        name = _decode_name(data[name_start : name_start + nlen])
        if not name or data_off + csize > len(data):
            continue
        entries.append(
            TnsEntry(
                name=name,
                method=method,
                crc32=crc32,
                compressed_size=csize,
                uncompressed_size=usize,
                local_header_offset=off,
                data_offset=data_off,
                name_len=nlen,
                extra_len=xlen,
                flags=flags,
                source="scan",
            )
        )
    return entries


def parse_tns(data: bytes) -> list[TnsEntry]:
    entries = _parse_central_directory(data)
    if entries:
        return entries
    return _scan_local_headers(data)


def entry_payload(data: bytes, entry: TnsEntry) -> bytes:
    return data[entry.data_offset : entry.data_end]


def describe_entries(data: bytes, entries: list[TnsEntry]) -> str:
    lines = []
    for entry in entries:
        payload = entry_payload(data, entry)
        display_name = entry.name.encode("ascii", errors="backslashreplace").decode("ascii")
        crc_note = ""
        if entry.method == 0:
            got = binascii.crc32(payload) & 0xFFFFFFFF
            crc_note = " ok" if got == entry.crc32 else f" got={got:08x}"
        lines.append(
            f"{display_name:30} method={entry.method:<3} "
            f"comp={entry.compressed_size:<8} uncomp={entry.uncompressed_size:<8} "
            f"crc={entry.crc32:08x}{crc_note} "
            f"local=0x{entry.local_header_offset:x} data=0x{entry.data_offset:x} "
            f"source={entry.source}"
        )
    return "\n".join(lines)


# ===========================================================================
# tns_method13.py — Decode TI-Nspire ZIP method 13 payloads
# ===========================================================================

HEADER_KEY = bytes.fromhex(
    "79 c4 e0 f4 5e ef 7a 5b "
    "70 13 7a 57 c2 fd 3d 2c "
    "c2 70 7c c1 ad 2f 15 75"
)

DEFAULT_BODY_KEY_MATERIAL = bytes.fromhex(
    "8d 24 ef 91 1c 6e b6 27 02 b5 38 e0 4b 13 e0 e9 d4 e0 3d 75 16"
)
DEFAULT_COUNTER_SEED = 0x6D657468

PHOENIX_DEFAULT = pathlib.Path(
    r"C:\Program Files\TI Education\TI-Nspire CX Student Software\lib\phoenix.dll"
)


class Method13Error(RuntimeError):
    pass


class TixcError(Method13Error):
    pass


class PureTixcExpander:
    """Pure Python TIXC expander."""

    def expand(self, tixc: bytes, expected_size: int | None = None) -> bytes:
        out = decode_tixc(tixc)
        if expected_size is not None and len(out) != expected_size:
            raise TixcError(f"pure TIXC output size {len(out)} does not match expected {expected_size}")
        return out


def _odd_parity(byte: int) -> int:
    byte &= 0xFE
    if byte.bit_count() % 2 == 0:
        byte |= 1
    return byte


def _key7_to_des_key(key7: bytes) -> bytes:
    # TI stores each DES key as 56 packed key bits. DES3 expects 8 bytes per
    # component key with odd parity bits, so expand 7 bytes -> 8 bytes here.
    if len(key7) != 7:
        raise ValueError("DES key packing requires exactly 7 bytes")
    b = list(key7)
    out = [
        b[0] & 0xFE,
        ((b[1] >> 1) & 0x7E) | ((b[0] << 7) & 0xFF),
        ((b[2] >> 2) & 0x3E) | ((b[1] << 6) & 0xFF),
        ((b[3] >> 3) & 0x1E) | ((b[2] << 5) & 0xFF),
        ((b[4] >> 4) & 0x0E) | ((b[3] << 4) & 0xFF),
        ((b[5] >> 5) & 0x06) | ((b[4] << 3) & 0xFF),
        ((b[6] >> 6) & 0x02) | ((b[5] << 2) & 0xFF),
        (b[6] << 1) & 0xFF,
    ]
    return bytes(_odd_parity(x) for x in out)


def decrypt_method13_to_tixc(payload: bytes) -> bytes:
    """Return the inflated TIXC stream from a method 13 payload."""
    if len(payload) < 40:
        raise Method13Error("method 13 payload is shorter than the 40-byte header")

    header = DES3.new(HEADER_KEY, DES3.MODE_ECB).decrypt(payload[:40])
    if not header.startswith(b"TIEN0100"):
        raise Method13Error(f"bad method 13 header magic: {header[:8]!r}")

    block_size = struct.unpack_from("<I", header, 8)[0]
    if block_size != 0x400:
        raise Method13Error(f"unsupported method 13 block size: 0x{block_size:x}")

    seed = struct.unpack_from("<I", header, 12)[0]
    key_material = header[16:37]
    encrypted = payload[40:]
    decrypted = _method13_crypt_body(encrypted, seed, key_material)

    try:
        return zlib.decompress(bytes(decrypted), -15)
    except zlib.error as exc:
        raise Method13Error(f"raw deflate stage failed: {exc}") from exc


def _method13_crypt_body(data: bytes, seed: int, key_material: bytes) -> bytes:
    if len(key_material) != 21:
        raise Method13Error("method 13 key material must be exactly 21 bytes")
    body_key = b"".join(_key7_to_des_key(key_material[i : i + 7]) for i in (0, 7, 14))
    cipher = DES3.new(body_key, DES3.MODE_ECB)

    out = bytearray()
    for off in range(0, len(data), 8):
        # The body transform is symmetric: 3DES-ECB encrypts a synthetic counter
        # block and XORs that keystream with the payload block.
        block_index = (off // 8) % 0x400
        counter = b"\x00\x00\x00\x00" + struct.pack("<I", (seed + block_index) & 0xFFFFFFFF)
        keystream = cipher.encrypt(counter)
        out.extend(a ^ b for a, b in zip(data[off : off + 8], keystream))
    return bytes(out)


def encrypt_tixc_to_method13(
    tixc: bytes,
    *,
    seed: int = DEFAULT_COUNTER_SEED,
    key_material: bytes = DEFAULT_BODY_KEY_MATERIAL,
    level: int = 9,
) -> bytes:
    """Encode a TIXC stream into a method 13 payload."""
    if not tixc.startswith(b"TIXC0100"):
        raise Method13Error("method 13 encoder expects a TIXC0100 stream")
    if len(key_material) != 21:
        raise Method13Error("method 13 key material must be exactly 21 bytes")

    compressor = zlib.compressobj(level=level, wbits=-15)
    deflated = compressor.compress(tixc) + compressor.flush()

    header = (
        b"TIEN0100"
        + struct.pack("<I", 0x400)
        + struct.pack("<I", seed & 0xFFFFFFFF)
        + key_material
        + b"\x00\x00\x00"
    )
    encrypted_header = DES3.new(HEADER_KEY, DES3.MODE_ECB).encrypt(header)
    encrypted_body = _method13_crypt_body(deflated, seed, key_material)
    return encrypted_header + encrypted_body


def decode_method13(
    payload: bytes,
    expected_size: int | None = None,
    *,
    tixc_backend: PureTixcExpander | None = None,
    allow_tixc_passthrough: bool = False,
) -> bytes:
    """Decode a method 13 payload to XML bytes when a TIXC backend is available."""
    tixc = decrypt_method13_to_tixc(payload)
    if not tixc.startswith(b"TIXC0100"):
        return tixc
    if tixc_backend is None:
        if allow_tixc_passthrough:
            return tixc
        raise TixcError("method 13 deflated successfully, but TIXC expansion needs a backend")
    try:
        return tixc_backend.expand(tixc, expected_size)
    except TixcDecodeError as exc:
        raise TixcError(str(exc)) from exc


# ===========================================================================
# tns_converter.py — Converter logic
# ===========================================================================

# ---------------------------------------------------------------------------
# TNS file reading/writing helpers
# ---------------------------------------------------------------------------

def decode_tns_entries(tns_path: pathlib.Path) -> dict[str, bytes]:
    data = tns_path.read_bytes()
    entries = parse_tns(data)
    if not entries:
        raise RuntimeError("No se encontraron entradas en el archivo TNS")

    backend = PureTixcExpander()
    result = {}
    for entry in entries:
        if not entry.name.lower().endswith(".xml"):
            continue
        payload = entry_payload(data, entry)
        if entry.method == 0:
            xml_bytes = payload
        elif entry.method == 8:
            xml_bytes = zlib.decompress(payload, -15)
        elif entry.method == 13:
            xml_bytes = decode_method13(payload, entry.uncompressed_size, tixc_backend=backend)
        else:
            continue
        result[entry.name] = xml_bytes
    return result


def _dos_datetime() -> tuple[int, int]:
    t = time.localtime()
    dos_time = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    dos_date = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return dos_time & 0xFFFF, dos_date & 0xFFFF


def build_tns(xml_files: dict[str, bytes], output_path: pathlib.Path) -> None:
    dos_time, dos_date = _dos_datetime()
    entries_info = []
    chunks = []
    offset = 0

    sorted_names = sorted(xml_files.keys(), key=lambda n: (0 if n.lower() == "document.xml" else 1, n.lower()))

    for i, name in enumerate(sorted_names):
        xml_data = xml_files[name]
        tixc = encode_tixc(xml_data)
        payload = encrypt_tixc_to_method13(tixc)
        crc = binascii.crc32(xml_data) & 0xFFFFFFFF

        name_bytes = name.encode("utf-8")
        fixed = struct.pack(
            "<HHHHHIIIHH",
            20, 0, 13, dos_time, dos_date,
            crc, len(payload), len(xml_data),
            len(name_bytes), 0,
        )

        if i == 0:
            header = b"*TIMLP0601" + fixed + name_bytes
        else:
            header = LOCAL_SIG + fixed + name_bytes

        entries_info.append({
            "name": name_bytes,
            "method": 13,
            "crc": crc,
            "comp_size": len(payload),
            "uncomp_size": len(xml_data),
            "local_offset": offset,
        })

        chunks.append(header)
        chunks.append(payload)
        offset += len(header) + len(payload)

    cd_offset = offset
    cd_chunks = []
    for info in entries_info:
        cd_entry = CD_SIG + struct.pack(
            "<HHHHHHIIIHHHHHII",
            20, 20, 0, info["method"], dos_time, dos_date,
            info["crc"], info["comp_size"], info["uncomp_size"],
            len(info["name"]), 0, 0, 0, 1, 0x20, info["local_offset"],
        ) + info["name"]
        cd_chunks.append(cd_entry)

    cd = b"".join(cd_chunks)
    eocd = struct.pack("<4sHHHHIIH", TIPD_SIG, 0, 0, len(entries_info), len(entries_info), len(cd), cd_offset, 0)

    output_path.write_bytes(b"".join(chunks) + cd + eocd)


# ---------------------------------------------------------------------------
# Document.xml template
# ---------------------------------------------------------------------------

DOCUMENT_XML_TEMPLATE = '<?xml version="1.0" encoding="UTF-8" ?><doc ver="1.0"><properties><product>28</product><platform>1</platform><swver>6.4.0.74 CAS </swver><date>{date}</date></properties><settings><assessmentMode>0</assessmentMode><lastview>1</lastview><readOnlyMode>0</readOnlyMode><lang>es</lang><dfmt>0</dfmt><tfmt>0</tfmt><curr>0</curr><expf>1</expf><ddig>7</ddig><angf>1</angf><exapp>1</exapp><cplxf>1</cplxf><unit>1</unit><casAndExactMode>1</casAndExactMode><vectf>1</vectf><base>1</base><gg_ddig>4</gg_ddig><gg_graphang>0</gg_graphang><gg_geomang>2</gg_geomang><gg_axisendv>1</gg_axisendv><gg_tooltipfunman>0</gg_tooltipfunman><gg_autopoi>1</gg_autopoi><gg_calcmenu>0</gg_calcmenu><gg_integerangles>0</gg_integerangles><gg_grid>0</gg_grid><gg_autolabeling>0</gg_autolabeling><ds_dispdig>0</ds_dispdig><ds_diagnostics>0</ds_diagnostics><gg_hideplotlabels>0</gg_hideplotlabels><boldnessFactor>0</boldnessFactor><examCode>0</examCode></settings><cardIntendedData><cardIntendedWidth>320</cardIntendedWidth><cardIntendedHeight>217</cardIntendedHeight><cardIntendedDensity>125.000000</cardIntendedDensity></cardIntendedData><rights></rights><nps>1</nps><imgsize>0</imgsize></doc>'


def make_document_xml() -> bytes:
    t = time.localtime()
    date_str = f"{t.tm_year}-{t.tm_mon}-{t.tm_mday}"
    return DOCUMENT_XML_TEMPLATE.format(date=date_str).encode("utf-8")


# ---------------------------------------------------------------------------
# Detect TNS content type
# ---------------------------------------------------------------------------

def detect_tns_type(xml_files: dict[str, bytes]) -> str:
    for name, data in xml_files.items():
        if name.lower().startswith("problem"):
            text = data.decode("utf-8", errors="replace")
            if "TI.Notepad" in text:
                return "notes"
            if "tabulator" in text:
                return "spreadsheet"
    return "unknown"


# ---------------------------------------------------------------------------
# Notes: TNS -> TXT
# ---------------------------------------------------------------------------

def extract_notes_text(problem_xml: bytes) -> str:
    root = ET.fromstring(problem_xml)
    fmtxt_content = None
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "fmtxt":
            fmtxt_content = elem.text
            break

    if not fmtxt_content:
        raise RuntimeError("No se encontró contenido de notas (fmtxt) en el archivo")

    inner = ET.fromstring(fmtxt_content)
    lines = []
    current_line = []

    for node in inner.iter():
        tag = node.tag
        if tag == "node":
            name = node.get("name", "")
            if name == "1para":
                if current_line:
                    lines.append("".join(current_line))
                    current_line = []
        elif tag == "leaf":
            text = node.text or ""
            current_line.append(text)

    if current_line:
        lines.append("".join(current_line))

    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def tns_to_txt(tns_path: pathlib.Path, txt_path: pathlib.Path) -> None:
    xml_files = decode_tns_entries(tns_path)
    for name, data in xml_files.items():
        if name.lower().startswith("problem"):
            text = extract_notes_text(data)
            txt_path.write_text(text, encoding="utf-8")
            print(f"Convertido: {tns_path} -> {txt_path}")
            print(f"  {len(text)} caracteres, {text.count(chr(10))+1} líneas")
            return
    raise RuntimeError("No se encontró Problem XML en el archivo TNS")


# ---------------------------------------------------------------------------
# Notes: TXT -> TNS
# ---------------------------------------------------------------------------

FORMAT_ENTRY_DEFAULT = '<formatEntry entryIndex="0" entryID="0" entryRefCnt="{refcnt}" tc="1" fc="268435199" fs="11" fst="0" cc="0" fest="0" feun="0" fesub="0" fesup="0" fn0="TI-Nspire Sans"></formatEntry>'


def _escape_xml_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_notes_fmtxt(text: str) -> str:
    lines = text.split("\n")
    word_count = 0
    for line in lines:
        words = re.findall(r'\S+\s*', line)
        word_count += len(words) if words else 1
    word_count += len(lines)

    parts = []
    parts.append(f'<r2dtotree version="1">')
    parts.append(f'<formatManager tableSize="1" capacity="2">')
    parts.append(FORMAT_ENTRY_DEFAULT.format(refcnt=word_count))
    parts.append(f'</formatManager>')
    parts.append(f'<node name="1page">')

    for line in lines:
        parts.append('<node name="1para"><node name="1rtline">')
        words = re.findall(r'\S+\s*', line)
        if not words:
            parts.append(f'<leaf name="1word" np="1" id0="0" pp0="0"/>')
        else:
            for word in words:
                escaped = _escape_xml_text(word)
                pp0 = len(word.encode("utf-8"))
                parts.append(f'<leaf name="1word" np="1" id0="0" pp0="{pp0}">{escaped}</leaf>')
        parts.append('</node></node>')

    parts.append('<node name="1para"><node name="1rtline">')
    parts.append('<leaf name="1word" np="1" id0="0" pp0="0"/>')
    parts.append('</node></node>')
    parts.append('</node></r2dtotree>')

    return "".join(parts)


def build_notes_problem_xml(text: str) -> bytes:
    fmtxt = build_notes_fmtxt(text)
    fmtxt_escaped = _escape_xml_text(fmtxt)

    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?>'
        '<prob xmlns="urn:TI.Problem" ver="1.0" pbname="">'
        '<sym></sym>'
        '<card clay="0" h1="10000" h2="10000" w1="10000" w2="10000">'
        '<isDummyCard>0</isDummyCard>'
        '<flag>0</flag>'
        '<wdgt xmlns:np="urn:TI.Notepad" type="TI.Notepad" ver="2.0">'
        '<np:mFlags>1024</np:mFlags>'
        '<np:value>3</np:value>'
        f'<np:fmtxt>{fmtxt_escaped}</np:fmtxt>'
        '</wdgt>'
        '</card></prob>'
    )
    return xml.encode("utf-8")


def txt_to_tns(txt_path: pathlib.Path, tns_path: pathlib.Path) -> None:
    text = txt_path.read_text(encoding="utf-8")
    doc_xml = make_document_xml()
    problem_xml = build_notes_problem_xml(text)
    build_tns({"Document.xml": doc_xml, "Problem1.xml": problem_xml}, tns_path)
    print(f"Convertido: {txt_path} -> {tns_path}")
    print(f"  Archivo TNS de notas creado ({tns_path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Spreadsheet: TNS -> CSV/XLSX
# ---------------------------------------------------------------------------

def extract_spreadsheet_data(problem_xml: bytes) -> tuple[list[str], list[list[str]]]:
    root = ET.fromstring(problem_xml)
    ns = {"tb": "urn:tabulator"}

    columns_data: list[tuple[str, dict[int, str]]] = []

    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "column" and elem.get("type") == "cell-column":
            col_name = ""
            cells: dict[int, str] = {}

            for child in elem:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag == "globalName":
                    col_name = child.text or ""
                elif ctag == "cells":
                    for cell in child:
                        cell_tag = cell.tag.split("}")[-1] if "}" in cell.tag else cell.tag
                        if cell_tag == "cell":
                            row_id = 0
                            value = ""
                            for cc in cell:
                                cctag = cc.tag.split("}")[-1] if "}" in cc.tag else cc.tag
                                if cctag == "rowId":
                                    row_id = int(cc.text or "0")
                                elif cctag == "formula":
                                    raw = cc.text or ""
                                    if raw.startswith('"') and raw.endswith('"'):
                                        value = raw[1:-1]
                                    elif _is_number(raw):
                                        value = raw
                                    elif raw:
                                        value = "=" + raw
                                    else:
                                        value = ""
                            if row_id > 0:
                                cells[row_id] = value

            columns_data.append((col_name, cells))

    if not columns_data:
        return [], []

    max_row = 0
    for _, cells in columns_data:
        if cells:
            max_row = max(max_row, max(cells.keys()))

    headers = [name for name, _ in columns_data]
    rows = []
    for r in range(1, max_row + 1):
        row = []
        for _, cells in columns_data:
            row.append(cells.get(r, ""))
        rows.append(row)

    while rows and all(c == "" for c in rows[-1]):
        rows.pop()

    while columns_data and not headers[-1] and not any(columns_data[-1][1].get(r+1, "") for r in range(len(rows))):
        headers.pop()
        columns_data.pop()
        for row in rows:
            if row:
                row.pop()

    return headers, rows


def tns_to_csv(tns_path: pathlib.Path, csv_path: pathlib.Path) -> None:
    xml_files = decode_tns_entries(tns_path)
    for name, data in xml_files.items():
        if name.lower().startswith("problem"):
            headers, rows = extract_spreadsheet_data(data)
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if any(h for h in headers):
                    writer.writerow(headers)
                for row in rows:
                    writer.writerow(row)
            total_cells = sum(1 for row in rows for c in row if c)
            print(f"Convertido: {tns_path} -> {csv_path}")
            print(f"  {len(headers)} columnas, {len(rows)} filas, {total_cells} celdas con datos")
            return
    raise RuntimeError("No se encontró Problem XML en el archivo TNS")


# ---------------------------------------------------------------------------
# Minimal pure-Python XLSX writer
# ---------------------------------------------------------------------------

XLSX_CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>'''

XLSX_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

XLSX_WORKBOOK = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''

XLSX_WORKBOOK_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>'''


def _col_letter(col: int) -> str:
    result = ""
    while col >= 0:
        result = chr(65 + col % 26) + result
        col = col // 26 - 1
    return result


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_xlsx(headers: list[str], rows: list[list[str]], path: pathlib.Path) -> None:
    shared_strings: list[str] = []
    ss_index: dict[str, int] = {}

    def get_ss_index(s: str) -> int:
        if s not in ss_index:
            ss_index[s] = len(shared_strings)
            shared_strings.append(s)
        return ss_index[s]

    sheet_rows = []

    if any(h for h in headers):
        cells_xml = []
        for c, h in enumerate(headers):
            ref = f"{_col_letter(c)}1"
            idx = get_ss_index(h)
            cells_xml.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        sheet_rows.append(f'<row r="1">{"".join(cells_xml)}</row>')

    start_row = 2 if any(h for h in headers) else 1
    for r_idx, row in enumerate(rows):
        cells_xml = []
        for c_idx, val in enumerate(row):
            if not val:
                continue
            ref = f"{_col_letter(c_idx)}{start_row + r_idx}"
            if val.startswith("="):
                formula = _escape_xml(val[1:])
                cells_xml.append(f'<c r="{ref}"><f>{formula}</f></c>')
            else:
                try:
                    num = float(val)
                    if num == int(num) and "." not in val:
                        cells_xml.append(f'<c r="{ref}"><v>{int(num)}</v></c>')
                    else:
                        cells_xml.append(f'<c r="{ref}"><v>{num}</v></c>')
                except ValueError:
                    idx = get_ss_index(val)
                    cells_xml.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        if cells_xml:
            sheet_rows.append(f'<row r="{start_row + r_idx}">{"".join(cells_xml)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        '</worksheet>'
    )

    ss_items = "".join(f"<si><t>{_escape_xml(s)}</t></si>" for s in shared_strings)
    ss_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        f'{ss_items}</sst>'
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", XLSX_CONTENT_TYPES)
        zf.writestr("_rels/.rels", XLSX_RELS)
        zf.writestr("xl/workbook.xml", XLSX_WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", XLSX_WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("xl/sharedStrings.xml", ss_xml)


def tns_to_xlsx(tns_path: pathlib.Path, xlsx_path: pathlib.Path) -> None:
    xml_files = decode_tns_entries(tns_path)
    for name, data in xml_files.items():
        if name.lower().startswith("problem"):
            headers, rows = extract_spreadsheet_data(data)
            write_xlsx(headers, rows, xlsx_path)
            total_cells = sum(1 for row in rows for c in row if c)
            print(f"Convertido: {tns_path} -> {xlsx_path}")
            print(f"  {len(headers)} columnas, {len(rows)} filas, {total_cells} celdas con datos")
            return
    raise RuntimeError("No se encontró Problem XML en el archivo TNS")


# ---------------------------------------------------------------------------
# Minimal pure-Python XLSX reader
# ---------------------------------------------------------------------------

def read_xlsx(path: pathlib.Path) -> tuple[list[str], list[list[str]]]:
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in ss_root.findall(".//s:si", ns):
                t_elem = si.find("s:t", ns)
                shared_strings.append(t_elem.text if t_elem is not None and t_elem.text else "")

        sheet_names = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        if not sheet_names:
            raise RuntimeError("No se encontró hoja de cálculo en el archivo XLSX")

        sheet_root = ET.fromstring(zf.read(sheet_names[0]))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        cell_data: dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0

        for row_elem in sheet_root.findall(".//s:row", ns):
            for cell_elem in row_elem.findall("s:c", ns):
                ref = cell_elem.get("r", "")
                cell_type = cell_elem.get("t", "")

                f_elem = cell_elem.find("s:f", ns)
                v_elem = cell_elem.find("s:v", ns)

                if f_elem is not None and f_elem.text:
                    value = "=" + f_elem.text
                elif v_elem is not None and v_elem.text:
                    value = v_elem.text
                    if cell_type == "s":
                        idx = int(value)
                        value = shared_strings[idx] if idx < len(shared_strings) else ""
                else:
                    value = ""

                col_str = re.match(r"([A-Z]+)", ref)
                row_str = re.search(r"(\d+)", ref)
                if col_str and row_str:
                    col = 0
                    for ch in col_str.group(1):
                        col = col * 26 + (ord(ch) - 64)
                    col -= 1
                    row = int(row_str.group(1)) - 1
                    cell_data[(row, col)] = value
                    max_row = max(max_row, row)
                    max_col = max(max_col, col)

    if not cell_data:
        return [], []

    headers = [cell_data.get((0, c), "") for c in range(max_col + 1)]
    has_header = any(h and not _is_number(h) for h in headers)

    if has_header:
        rows = []
        for r in range(1, max_row + 1):
            row = [cell_data.get((r, c), "") for c in range(max_col + 1)]
            rows.append(row)
        return headers, rows
    else:
        rows = []
        for r in range(0, max_row + 1):
            row = [cell_data.get((r, c), "") for c in range(max_col + 1)]
            rows.append(row)
        return [""] * (max_col + 1), rows


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Spreadsheet: CSV/XLSX -> TNS
# ---------------------------------------------------------------------------

def _format_cell_value(val: str) -> str:
    if not val:
        return ""
    if val.startswith("="):
        return val[1:]
    try:
        float(val)
        return val
    except ValueError:
        return f'"{val}"'


def build_spreadsheet_problem_xml(
    headers: list[str],
    rows: list[list[str]],
    num_columns: int = 26,
) -> bytes:
    ns_tb = "urn:tabulator"
    ns_prob = "urn:TI.Problem"
    ns_ft = "urn:TI.FunctionTable"

    num_columns = max(num_columns, len(headers))

    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8" ?>')
    parts.append(f'<prob xmlns="{ns_prob}" ver="1.0" pbname="">')
    parts.append('<sym></sym>')
    parts.append('<card clay="0" h1="10000" h2="10000" w1="10000" w2="10000">')
    parts.append('<isDummyCard>0</isDummyCard>')
    parts.append('<flag>0</flag>')
    parts.append(f'<wdgt xmlns:tb="{ns_tb}" type="tabulator" ver="1.0">')
    parts.append('<tb:mFlags>1024</tb:mFlags>')
    parts.append('<tb:value>2</tb:value>')
    parts.append('<tb:cry>0</tb:cry>')
    parts.append('<tb:legal>none</tb:legal>')
    parts.append('<tb:schk>false</tb:schk>')
    parts.append('<tb:guid>00000000000000000000000000000000</tb:guid>')
    parts.append('<tb:showingLnS>1</tb:showingLnS>')
    parts.append('<tb:table>')
    parts.append('<tb:rowHeights></tb:rowHeights>')
    parts.append('<tb:columns>')

    for col_idx in range(num_columns):
        parts.append('<tb:column type="cell-column">')

        if col_idx < len(headers) and headers[col_idx]:
            parts.append(f'<tb:globalName>{_escape_xml_text(headers[col_idx])}</tb:globalName>')

        parts.append('<tb:columnWidthNative>70</tb:columnWidthNative>')
        parts.append('<tb:columnWidth>70</tb:columnWidth>')
        parts.append('<tb:columnFlags>0</tb:columnFlags>')
        parts.append('<tb:cells>')

        if col_idx < len(headers):
            for row_idx, row in enumerate(rows):
                if col_idx < len(row) and row[col_idx]:
                    formatted = _format_cell_value(row[col_idx])
                    parts.append('<tb:cell>')
                    parts.append(f'<tb:rowId>{row_idx + 1}</tb:rowId>')
                    parts.append(f'<tb:formula>{_escape_xml_text(formatted)}</tb:formula>')
                    parts.append(f'<tb:data>{_escape_xml_text(formatted)}</tb:data>')
                    parts.append('</tb:cell>')

        parts.append('</tb:cells>')
        parts.append('</tb:column>')

    parts.append('</tb:columns>')
    parts.append('</tb:table>')

    color_str = "00" * num_columns
    parts.append(f'<tb:color version="2.0"><tb:columns>{color_str}</tb:columns></tb:color>')

    parts.append(f'<tb:functiontable xmlns:tb="{ns_ft}">')
    parts.append('<tb:defaultColumnWidth>70</tb:defaultColumnWidth>')
    parts.append('<tb:defaultIndependantStartValue>0.0</tb:defaultIndependantStartValue>')
    parts.append('<tb:defaultIndependantStepValue>1.0</tb:defaultIndependantStepValue>')
    parts.append('<tb:defaultIndependantAutoModeValue>1</tb:defaultIndependantAutoModeValue>')
    parts.append('<tb:defaultDependantAutoModeValue>1</tb:defaultDependantAutoModeValue>')
    parts.append('<tb:table><tb:columns>')
    parts.append('<tb:column type="function table independant column">')
    parts.append('<tb:columnWidthNative>70</tb:columnWidthNative>')
    parts.append('<tb:columnWidth>70</tb:columnWidth>')
    parts.append('<tb:columnFlags>0</tb:columnFlags>')
    parts.append('<tb:nvColumnWidth>0</tb:nvColumnWidth>')
    parts.append('<tb:autoSize>1</tb:autoSize>')
    parts.append('</tb:column>')
    parts.append('<tb:column type="function table dependant column">')
    parts.append('<tb:columnWidthNative>234</tb:columnWidthNative>')
    parts.append('<tb:columnWidth>234</tb:columnWidth>')
    parts.append('<tb:columnFlags>0</tb:columnFlags>')
    parts.append('<tb:nvColumnWidth>0</tb:nvColumnWidth>')
    parts.append('</tb:column>')
    parts.append('</tb:columns></tb:table>')
    parts.append('</tb:functiontable>')
    parts.append('</wdgt>')
    parts.append('</card></prob>')

    return "".join(parts).encode("utf-8")


def csv_to_tns(csv_path: pathlib.Path, tns_path: pathlib.Path) -> None:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        all_rows = list(reader)

    if not all_rows:
        raise RuntimeError("El archivo CSV está vacío")

    first_row = all_rows[0]
    has_header = any(not _is_number(v) for v in first_row if v)

    if has_header:
        headers = first_row
        rows = all_rows[1:]
    else:
        headers = [""] * len(first_row)
        rows = all_rows

    doc_xml = make_document_xml()
    problem_xml = build_spreadsheet_problem_xml(headers, rows)
    build_tns({"Document.xml": doc_xml, "Problem1.xml": problem_xml}, tns_path)

    total_cells = sum(1 for row in rows for c in row if c)
    print(f"Convertido: {csv_path} -> {tns_path}")
    print(f"  {len(headers)} columnas, {len(rows)} filas, {total_cells} celdas con datos")


def xlsx_to_tns(xlsx_path: pathlib.Path, tns_path: pathlib.Path) -> None:
    headers, rows = read_xlsx(xlsx_path)

    doc_xml = make_document_xml()
    problem_xml = build_spreadsheet_problem_xml(headers, rows)
    build_tns({"Document.xml": doc_xml, "Problem1.xml": problem_xml}, tns_path)

    total_cells = sum(1 for row in rows for c in row if c)
    print(f"Convertido: {xlsx_path} -> {tns_path}")
    print(f"  {len(headers)} columnas, {len(rows)} filas, {total_cells} celdas con datos")


# ---------------------------------------------------------------------------
# Auto-detection converter
# ---------------------------------------------------------------------------

def convert(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    in_ext = input_path.suffix.lower()
    out_ext = output_path.suffix.lower()

    if in_ext == ".tns":
        xml_files = decode_tns_entries(input_path)
        tns_type = detect_tns_type(xml_files)

        if out_ext == ".txt":
            if tns_type != "notes":
                print(f"Advertencia: el archivo TNS parece ser '{tns_type}', no notas. Intentando extraer como notas...")
            tns_to_txt(input_path, output_path)

        elif out_ext == ".csv":
            if tns_type != "spreadsheet":
                print(f"Advertencia: el archivo TNS parece ser '{tns_type}', no hoja de cálculo. Intentando extraer...")
            tns_to_csv(input_path, output_path)

        elif out_ext == ".xlsx":
            if tns_type != "spreadsheet":
                print(f"Advertencia: el archivo TNS parece ser '{tns_type}', no hoja de cálculo. Intentando extraer...")
            tns_to_xlsx(input_path, output_path)

        else:
            if tns_type == "notes":
                output_path = output_path.with_suffix(".txt")
                tns_to_txt(input_path, output_path)
            elif tns_type == "spreadsheet":
                output_path = output_path.with_suffix(".xlsx")
                tns_to_xlsx(input_path, output_path)
            else:
                raise RuntimeError(f"Tipo de contenido TNS no reconocido: {tns_type}")

    elif in_ext == ".txt" and out_ext == ".tns":
        txt_to_tns(input_path, output_path)

    elif in_ext == ".csv" and out_ext == ".tns":
        csv_to_tns(input_path, output_path)

    elif in_ext == ".xlsx" and out_ext == ".tns":
        xlsx_to_tns(input_path, output_path)

    else:
        raise RuntimeError(
            f"Conversión no soportada: {in_ext} -> {out_ext}\n"
            "Conversiones válidas:\n"
            "  .tns -> .txt   (notas)\n"
            "  .tns -> .csv   (hoja de cálculo)\n"
            "  .tns -> .xlsx  (hoja de cálculo)\n"
            "  .txt -> .tns   (crear notas)\n"
            "  .csv -> .tns   (crear hoja de cálculo)\n"
            "  .xlsx -> .tns  (crear hoja de cálculo)"
        )


# ===========================================================================
# app.py — Web server and HTML UI
# ===========================================================================

PORT = 8051

HTML_PAGE = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TNS Converter</title>
<style>
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #242836;
  --border: #2e3348;
  --text: #e4e6f0;
  --text2: #9298b0;
  --accent: #6c8cff;
  --accent-hover: #8aa4ff;
  --accent-bg: rgba(108,140,255,0.1);
  --green: #4ade80;
  --green-bg: rgba(74,222,128,0.1);
  --red: #f87171;
  --orange: #fb923c;
  --radius: 12px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 20px;
}

header {
  text-align: center;
  padding: 32px 0 24px;
}
header h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.5px;
}
header h1 span { color: var(--accent); }
header p {
  color: var(--text2);
  margin-top: 8px;
  font-size: 15px;
}

/* Drop zone */
.dropzone {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--surface);
  margin-bottom: 24px;
}
.dropzone:hover, .dropzone.dragover {
  border-color: var(--accent);
  background: var(--accent-bg);
}
.dropzone svg {
  width: 48px; height: 48px;
  color: var(--text2);
  margin-bottom: 12px;
}
.dropzone.dragover svg { color: var(--accent); }
.dropzone h3 { font-size: 18px; margin-bottom: 6px; }
.dropzone p { color: var(--text2); font-size: 14px; }
.dropzone input { display: none; }

/* Panels */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 20px;
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 10px;
}
.panel-header h2 {
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}
.badge-notes { background: var(--accent-bg); color: var(--accent); }
.badge-sheet { background: var(--green-bg); color: var(--green); }
.panel-body { padding: 20px; }

/* Text editor */
#notes-editor {
  width: 100%;
  min-height: 320px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.6;
  padding: 16px;
  resize: vertical;
  outline: none;
}
#notes-editor:focus {
  border-color: var(--accent);
}

/* Table editor */
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
thead th {
  background: var(--surface2);
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid var(--border);
  position: sticky;
  top: 0;
}
thead th input {
  width: 100%;
  background: transparent;
  border: none;
  color: var(--accent);
  font-weight: 600;
  font-size: 14px;
  outline: none;
  padding: 2px 0;
}
thead th input::placeholder { color: var(--text2); }
td {
  padding: 2px;
  border-bottom: 1px solid var(--border);
}
td input {
  width: 100%;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text);
  font-size: 14px;
  padding: 8px 10px;
  outline: none;
}
td input:focus {
  border-color: var(--accent);
  background: var(--accent-bg);
}
tr:hover td { background: rgba(255,255,255,0.02); }
.row-num {
  color: var(--text2);
  font-size: 12px;
  text-align: center;
  width: 40px;
  min-width: 40px;
  padding: 10px 8px;
  user-select: none;
}

/* Table controls */
.table-controls {
  display: flex;
  gap: 8px;
  padding: 12px 0 0;
  flex-wrap: wrap;
}

/* Buttons */
.btn-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  text-decoration: none;
}
.btn:hover {
  border-color: var(--accent);
  background: var(--accent-bg);
}
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.btn-primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}
.btn-sm { padding: 6px 14px; font-size: 13px; }
.btn-green { border-color: var(--green); color: var(--green); }
.btn-green:hover { background: var(--green-bg); }

/* Status */
.status {
  padding: 12px 16px;
  border-radius: 8px;
  margin-top: 16px;
  font-size: 14px;
  display: none;
}
.status.show { display: block; }
.status.ok { background: var(--green-bg); color: var(--green); }
.status.err { background: rgba(248,113,113,0.1); color: var(--red); }
.status.info { background: var(--accent-bg); color: var(--accent); }

/* New file buttons */
.new-section {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

/* Footer */
footer {
  text-align: center;
  padding: 24px 0;
  color: var(--text2);
  font-size: 13px;
}

/* Hidden */
.hidden { display: none !important; }

/* Responsive */
@media (max-width: 640px) {
  .container { padding: 16px 12px; }
  header h1 { font-size: 22px; }
  .dropzone { padding: 32px 16px; }
  #notes-editor { min-height: 200px; font-size: 13px; }
}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1><span>TNS</span> Converter</h1>
    <p>Convierte archivos TI-Nspire (.tns) para editarlos y reconvertirlos</p>
  </header>

  <div class="new-section">
    <button class="btn" onclick="newNotes()">+ Crear notas nuevas</button>
    <button class="btn" onclick="newSheet()">+ Crear hoja de calculo nueva</button>
  </div>

  <div class="dropzone" id="dropzone">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M12 16V4m0 0L8 8m4-4l4 4M4 14v4a2 2 0 002 2h12a2 2 0 002-2v-4"/>
    </svg>
    <h3>Arrastra un archivo .tns aqui</h3>
    <p>o haz clic para seleccionar — tambien acepta .txt, .csv, .xlsx</p>
    <input type="file" id="fileInput" accept=".tns,.txt,.csv,.xlsx">
  </div>

  <!-- Notes editor -->
  <div id="notes-panel" class="panel hidden">
    <div class="panel-header">
      <h2><span class="badge badge-notes">Notas</span> <span id="notes-filename"></span></h2>
      <div class="btn-row">
        <button class="btn btn-sm" onclick="downloadTxt()">Descargar .txt</button>
        <button class="btn btn-sm btn-primary" onclick="downloadTns('notes')">Descargar .tns</button>
      </div>
    </div>
    <div class="panel-body">
      <textarea id="notes-editor" placeholder="Escribe tus notas aqui..."></textarea>
    </div>
  </div>

  <!-- Spreadsheet editor -->
  <div id="sheet-panel" class="panel hidden">
    <div class="panel-header">
      <h2><span class="badge badge-sheet">Hoja de calculo</span> <span id="sheet-filename"></span></h2>
      <div class="btn-row">
        <button class="btn btn-sm" onclick="downloadCsv()">Descargar .csv</button>
        <button class="btn btn-sm" onclick="downloadXlsx()">Descargar .xlsx</button>
        <button class="btn btn-sm btn-primary" onclick="downloadTns('sheet')">Descargar .tns</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="table-wrap">
        <table id="sheet-table">
          <thead id="sheet-head"></thead>
          <tbody id="sheet-body"></tbody>
        </table>
      </div>
      <div class="table-controls">
        <button class="btn btn-sm" onclick="addRow()">+ Fila</button>
        <button class="btn btn-sm" onclick="addCol()">+ Columna</button>
        <button class="btn btn-sm" onclick="removeLastRow()">- Fila</button>
        <button class="btn btn-sm" onclick="removeLastCol()">- Columna</button>
      </div>
    </div>
  </div>

  <div id="status" class="status"></div>

  <footer>
    TNS Converter &mdash; herramienta local, tus archivos nunca salen de tu computadora
  </footer>
</div>

<script>
let currentMode = null; // 'notes' or 'sheet'
let currentFilename = '';
let sheetHeaders = [];
let sheetRows = [];
let sheetNumCols = 5;
let sheetNumRows = 10;

// ---- Drop zone ----
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});

function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  currentFilename = file.name.replace(/\.[^.]+$/, '');

  const reader = new FileReader();
  reader.onload = async () => {
    const data = new Uint8Array(reader.result);
    const b64 = arrayToBase64(data);

    if (ext === 'tns') {
      await uploadTns(b64, file.name);
    } else if (ext === 'txt') {
      const text = new TextDecoder('utf-8').decode(data);
      showNotes(text, file.name);
    } else if (ext === 'csv') {
      const text = new TextDecoder('utf-8').decode(data);
      parseCsvAndShow(text, file.name);
    } else if (ext === 'xlsx') {
      await uploadXlsx(b64, file.name);
    } else {
      showStatus('Formato no soportado. Usa .tns, .txt, .csv o .xlsx', 'err');
    }
  };
  reader.readAsArrayBuffer(file);
}

function arrayToBase64(arr) {
  let bin = '';
  for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin);
}

function base64ToArray(b64) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

// ---- API calls ----
async function apiPost(endpoint, body) {
  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  return resp.json();
}

async function uploadTns(b64, filename) {
  showStatus('Decodificando archivo TNS...', 'info');
  const result = await apiPost('/api/decode-tns', {data: b64, filename});
  if (result.error) { showStatus('Error: ' + result.error, 'err'); return; }

  if (result.type === 'notes') {
    showNotes(result.text, filename);
    showStatus('Notas cargadas correctamente', 'ok');
  } else if (result.type === 'spreadsheet') {
    showSheet(result.headers, result.rows, filename);
    showStatus('Hoja de calculo cargada correctamente', 'ok');
  } else {
    showStatus('Tipo de archivo TNS no reconocido', 'err');
  }
}

async function uploadXlsx(b64, filename) {
  showStatus('Leyendo archivo XLSX...', 'info');
  const result = await apiPost('/api/decode-xlsx', {data: b64});
  if (result.error) { showStatus('Error: ' + result.error, 'err'); return; }
  showSheet(result.headers, result.rows, filename);
  showStatus('Hoja de calculo cargada correctamente', 'ok');
}

async function downloadTns(mode) {
  showStatus('Generando archivo TNS...', 'info');
  let body;
  if (mode === 'notes') {
    body = {type: 'notes', text: document.getElementById('notes-editor').value};
  } else {
    collectSheetData();
    body = {type: 'spreadsheet', headers: sheetHeaders, rows: sheetRows};
  }
  const result = await apiPost('/api/build-tns', body);
  if (result.error) { showStatus('Error: ' + result.error, 'err'); return; }

  const data = base64ToArray(result.data);
  downloadBlob(data, (currentFilename || 'archivo') + '.tns', 'application/octet-stream');
  showStatus('Archivo .tns descargado', 'ok');
}

function downloadTxt() {
  const text = document.getElementById('notes-editor').value;
  const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = (currentFilename || 'notas') + '.txt'; a.click();
  URL.revokeObjectURL(url);
  showStatus('Archivo .txt descargado', 'ok');
}

function downloadCsv() {
  collectSheetData();
  let csv = '';
  if (sheetHeaders.some(h => h)) csv += sheetHeaders.map(escapeCsv).join(',') + '\n';
  for (const row of sheetRows) csv += row.map(escapeCsv).join(',') + '\n';
  const blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = (currentFilename || 'hoja') + '.csv'; a.click();
  URL.revokeObjectURL(url);
  showStatus('Archivo .csv descargado', 'ok');
}

async function downloadXlsx() {
  collectSheetData();
  showStatus('Generando archivo XLSX...', 'info');
  const result = await apiPost('/api/build-xlsx', {headers: sheetHeaders, rows: sheetRows});
  if (result.error) { showStatus('Error: ' + result.error, 'err'); return; }
  const data = base64ToArray(result.data);
  downloadBlob(data, (currentFilename || 'hoja') + '.xlsx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  showStatus('Archivo .xlsx descargado', 'ok');
}

function downloadBlob(uint8, filename, mime) {
  const blob = new Blob([uint8], {type: mime});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function escapeCsv(val) {
  if (!val) return '';
  if (val.includes(',') || val.includes('"') || val.includes('\n'))
    return '"' + val.replace(/"/g, '""') + '"';
  return val;
}

// ---- UI ----
function showNotes(text, filename) {
  currentMode = 'notes';
  document.getElementById('notes-panel').classList.remove('hidden');
  document.getElementById('sheet-panel').classList.add('hidden');
  document.getElementById('notes-editor').value = text;
  document.getElementById('notes-filename').textContent = filename || '';
}

function showSheet(headers, rows, filename) {
  currentMode = 'sheet';
  document.getElementById('sheet-panel').classList.remove('hidden');
  document.getElementById('notes-panel').classList.add('hidden');
  document.getElementById('sheet-filename').textContent = filename || '';

  sheetHeaders = headers.length ? [...headers] : Array(5).fill('');
  sheetRows = rows.length ? rows.map(r => [...r]) : [];
  sheetNumCols = sheetHeaders.length;

  // Ensure minimum size
  while (sheetNumCols < 5) { sheetHeaders.push(''); sheetNumCols++; }
  while (sheetRows.length < 10) sheetRows.push(Array(sheetNumCols).fill(''));
  for (let r of sheetRows) while (r.length < sheetNumCols) r.push('');

  sheetNumRows = sheetRows.length;
  renderTable();
}

function renderTable() {
  const thead = document.getElementById('sheet-head');
  const tbody = document.getElementById('sheet-body');

  // Headers
  let hrow = '<tr><th class="row-num">#</th>';
  for (let c = 0; c < sheetNumCols; c++) {
    const val = (sheetHeaders[c] || '').replace(/"/g, '&quot;');
    const letter = String.fromCharCode(65 + (c % 26));
    hrow += `<th><input type="text" value="${val}" placeholder="${letter}" data-col="${c}" onchange="updateHeader(this)"></th>`;
  }
  hrow += '</tr>';
  thead.innerHTML = hrow;

  // Body
  let html = '';
  for (let r = 0; r < sheetNumRows; r++) {
    html += `<tr><td class="row-num">${r+1}</td>`;
    for (let c = 0; c < sheetNumCols; c++) {
      const val = (sheetRows[r]?.[c] || '').replace(/"/g, '&quot;');
      html += `<td><input type="text" value="${val}" data-row="${r}" data-col="${c}" onchange="updateCell(this)"></td>`;
    }
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

function updateHeader(el) {
  sheetHeaders[parseInt(el.dataset.col)] = el.value;
}

function updateCell(el) {
  const r = parseInt(el.dataset.row);
  const c = parseInt(el.dataset.col);
  if (!sheetRows[r]) sheetRows[r] = Array(sheetNumCols).fill('');
  sheetRows[r][c] = el.value;
}

function collectSheetData() {
  // Read current values from DOM
  document.querySelectorAll('#sheet-head input').forEach(el => {
    sheetHeaders[parseInt(el.dataset.col)] = el.value;
  });
  document.querySelectorAll('#sheet-body input').forEach(el => {
    const r = parseInt(el.dataset.row);
    const c = parseInt(el.dataset.col);
    if (!sheetRows[r]) sheetRows[r] = Array(sheetNumCols).fill('');
    sheetRows[r][c] = el.value;
  });
}

function addRow() {
  collectSheetData();
  sheetRows.push(Array(sheetNumCols).fill(''));
  sheetNumRows++;
  renderTable();
}

function addCol() {
  collectSheetData();
  sheetHeaders.push('');
  sheetNumCols++;
  for (let r of sheetRows) r.push('');
  renderTable();
}

function removeLastRow() {
  if (sheetNumRows <= 1) return;
  collectSheetData();
  sheetRows.pop();
  sheetNumRows--;
  renderTable();
}

function removeLastCol() {
  if (sheetNumCols <= 1) return;
  collectSheetData();
  sheetHeaders.pop();
  sheetNumCols--;
  for (let r of sheetRows) r.pop();
  renderTable();
}

function newNotes() {
  currentFilename = 'notas';
  showNotes('', 'Nuevas notas');
  showStatus('Editor de notas listo', 'ok');
}

function newSheet() {
  currentFilename = 'hoja';
  showSheet([], [], 'Nueva hoja de calculo');
  showStatus('Editor de hoja de calculo listo', 'ok');
}

function parseCsvAndShow(text, filename) {
  const lines = text.split('\n').filter(l => l.trim());
  if (!lines.length) { showStatus('CSV vacio', 'err'); return; }
  const rows = lines.map(l => {
    // Simple CSV parse
    const result = [];
    let current = '', inQuotes = false;
    for (let i = 0; i < l.length; i++) {
      const ch = l[i];
      if (inQuotes) {
        if (ch === '"' && l[i+1] === '"') { current += '"'; i++; }
        else if (ch === '"') inQuotes = false;
        else current += ch;
      } else {
        if (ch === '"') inQuotes = true;
        else if (ch === ',') { result.push(current); current = ''; }
        else current += ch;
      }
    }
    result.push(current);
    return result;
  });

  const firstRow = rows[0];
  const hasHeader = firstRow.some(v => v && isNaN(Number(v)));
  if (hasHeader) {
    showSheet(firstRow, rows.slice(1), filename);
  } else {
    showSheet(Array(firstRow.length).fill(''), rows, filename);
  }
  showStatus('CSV cargado correctamente', 'ok');
}

function showStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status show ' + type;
  if (type === 'ok' || type === 'info') setTimeout(() => el.classList.remove('show'), 4000);
}
</script>
</body>
</html>
'''


class TNSHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        try:
            if self.path == "/api/decode-tns":
                result = self._decode_tns(body)
            elif self.path == "/api/decode-xlsx":
                result = self._decode_xlsx(body)
            elif self.path == "/api/build-tns":
                result = self._build_tns(body)
            elif self.path == "/api/build-xlsx":
                result = self._build_xlsx(body)
            else:
                self.send_error(404)
                return
        except Exception as e:
            result = {"error": str(e)}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode("utf-8"))

    def _decode_tns(self, body: dict) -> dict:
        data = base64.b64decode(body["data"])
        tmp = pathlib.Path("/tmp/tns_converter_input.tns")
        tmp.write_bytes(data)

        xml_files = decode_tns_entries(tmp)
        tns_type = detect_tns_type(xml_files)

        if tns_type == "notes":
            for name, xml_data in xml_files.items():
                if name.lower().startswith("problem"):
                    text = extract_notes_text(xml_data)
                    return {"type": "notes", "text": text}

        elif tns_type == "spreadsheet":
            for name, xml_data in xml_files.items():
                if name.lower().startswith("problem"):
                    headers, rows = extract_spreadsheet_data(xml_data)
                    return {"type": "spreadsheet", "headers": headers, "rows": rows}

        return {"error": f"Tipo TNS no reconocido: {tns_type}"}

    def _decode_xlsx(self, body: dict) -> dict:
        data = base64.b64decode(body["data"])
        tmp = pathlib.Path("/tmp/tns_converter_input.xlsx")
        tmp.write_bytes(data)

        headers, rows = read_xlsx(tmp)
        return {"headers": headers, "rows": rows}

    def _build_tns(self, body: dict) -> dict:
        doc_xml = make_document_xml()

        if body["type"] == "notes":
            problem_xml = build_notes_problem_xml(body["text"])
        else:
            headers = body.get("headers", [])
            rows = body.get("rows", [])
            # Filter out fully empty trailing rows/cols
            while rows and all(c == "" for c in rows[-1]):
                rows.pop()
            problem_xml = build_spreadsheet_problem_xml(headers, rows)

        tmp = pathlib.Path("/tmp/tns_converter_output.tns")
        build_tns({"Document.xml": doc_xml, "Problem1.xml": problem_xml}, tmp)
        return {"data": base64.b64encode(tmp.read_bytes()).decode("ascii")}

    def _build_xlsx(self, body: dict) -> dict:
        headers = body.get("headers", [])
        rows = body.get("rows", [])
        tmp = pathlib.Path("/tmp/tns_converter_output.xlsx")
        write_xlsx(headers, rows, tmp)
        return {"data": base64.b64encode(tmp.read_bytes()).decode("ascii")}


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    allow_reuse_port = True


def main():
    with ReusableTCPServer(("127.0.0.1", PORT), TNSHandler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"TNS Converter corriendo en {url}")
        print("Presiona Ctrl+C para detener\n")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDetenido.")


if __name__ == "__main__":
    main()
