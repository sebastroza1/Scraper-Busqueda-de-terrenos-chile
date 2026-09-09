from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_PREFIX = "LandfinderChile:"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_windows_secret(key: str) -> str | None:
    if sys.platform != "win32":
        return None
    advapi32 = ctypes.windll.advapi32
    credential = ctypes.POINTER(_Credential)()
    ok = advapi32.CredReadW(
        f"{_PREFIX}{key}",
        _CRED_TYPE_GENERIC,
        0,
        ctypes.byref(credential),
    )
    if not ok:
        return None
    try:
        blob_size = credential.contents.CredentialBlobSize
        blob = credential.contents.CredentialBlob
        if not blob or blob_size <= 0:
            return None
        return bytes(blob[:blob_size]).decode("utf-8")
    finally:
        advapi32.CredFree(credential)


def write_windows_secret(key: str, value: str) -> bool:
    if sys.platform != "win32" or not value:
        return False
    encoded = value.encode("utf-8")
    blob = (ctypes.c_ubyte * len(encoded))(*encoded)
    credential = _Credential()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = f"{_PREFIX}{key}"
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = blob
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "Landfinder"
    return bool(ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0))
