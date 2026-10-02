"""Minimal ctypes wrapper over the Windows Performance Data Helper (pdh.dll). No dependencies."""
import ctypes
import os
from ctypes import wintypes

PDH_FMT_DOUBLE, PDH_FMT_NOCAP100 = 0x00000200, 0x00008000
PDH_MORE_DATA = 0x800007D2
VALID = (0, 1)  # PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA


class _Value(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _Value)]


_pdh = ctypes.WinDLL("pdh") if os.name == "nt" else None
_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
if _pdh:
    for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
               "PdhGetFormattedCounterArrayW", "PdhCloseQuery"):
        getattr(_pdh, fn).restype = wintypes.DWORD
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _check(status, what):
    if status != 0:
        raise OSError(f"{what} failed: 0x{status:08X}")


class Query:
    """Wildcard counters; call collect() once per interval, then values(path)."""

    def __init__(self, paths):
        if _pdh is None:
            raise OSError("npu-top needs Windows (it reads Windows performance counters)")
        self._q = ctypes.c_void_p()
        _check(_pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._q)), "PdhOpenQuery")
        self._counters = {}
        for p in paths:
            h = ctypes.c_void_p()
            _check(_pdh.PdhAddEnglishCounterW(self._q, p, 0, ctypes.byref(h)), f"PdhAddCounter({p})")
            self._counters[p] = h
        self.collect()  # rate counters need a first sample to diff against

    def collect(self):
        _check(_pdh.PdhCollectQueryData(self._q), "PdhCollectQueryData")

    def values(self, path):
        """{instance_name: value} for the last collect(); empty if the counter has no instances yet."""
        h, size, count = self._counters[path], wintypes.DWORD(0), wintypes.DWORD(0)
        fmt = PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
        status = _pdh.PdhGetFormattedCounterArrayW(h, fmt, ctypes.byref(size), ctypes.byref(count), None)
        if status != PDH_MORE_DATA:
            return {}
        buf = ctypes.create_string_buffer(size.value)
        status = _pdh.PdhGetFormattedCounterArrayW(h, fmt, ctypes.byref(size), ctypes.byref(count), buf)
        if status != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(_Item))
        return {items[i].szName: items[i].FmtValue.doubleValue
                for i in range(count.value) if items[i].FmtValue.CStatus in VALID}

    def close(self):
        _pdh.PdhCloseQuery(self._q)


def process_name(pid):
    h = _k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return "<protected>" if pid else "<system>"
    buf, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
    ok = _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    _k32.CloseHandle(h)
    return os.path.basename(buf.value) if ok else "<protected>"
