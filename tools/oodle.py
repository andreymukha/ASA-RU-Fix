"""Reusable ctypes interface to the bootstrap-built GPL ooz decoder."""
import ctypes
import struct
import sys
from pathlib import Path

from tools.pakv12 import PakError


class OozBackend:
    def __init__(self):
        if sys.platform != 'win32' or struct.calcsize('P') != 8:
            raise PakError('The ooz backend requires Windows x64 and 64-bit Python')
        path = Path(__file__).resolve().parents[1] / 'work/tools/ooz/ooz.dll'
        if not path.is_file():
            raise PakError('ooz DLL is absent; run python tools/bootstrap.py')
        try:
            self.library = ctypes.CDLL(str(path))
        except OSError as exc:
            raise PakError(f'Cannot load bootstrap ooz DLL: {exc}') from exc
        self.call = self.library.asa_ooz_decompress
        self.call.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        self.call.restype = ctypes.c_int

    def decompress(self, source: bytes, size: int) -> bytes:
        # Upstream explicitly requires 64 spare output bytes (vector stores).
        # Pad input too, retaining its actual length for the decoder.
        src = ctypes.create_string_buffer(source, len(source) + 64)
        dst = ctypes.create_string_buffer(size + 64)
        result = self.call(src, len(source), dst, size)
        if result != size:
            raise PakError(f'ooz decompression failed: returned {result}, expected {size}')
        return dst.raw[:size]
