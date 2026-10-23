"""Optional example builder: call installed Windows SAPI directly through COM.

No downloaded library, shell script, execution-policy change or network service.
Only used to synthesize the authored fictional-data example.
"""
from __future__ import annotations

import ctypes as C
import os
import wave
from pathlib import Path


def synthesize(document: dict, assets: Path, *, replace: bool = False) -> None:
    if os.name != "nt":
        raise OSError("Local SAPI example synthesis requires Windows")
    ole32, oleaut = C.OleDLL("ole32"), C.WinDLL("oleaut32")
    HRESULT, DWORD, DISPID = C.c_long, C.c_ulong, C.c_long

    class GUID(C.Structure):
        _fields_ = [("a", DWORD), ("b", C.c_ushort), ("c", C.c_ushort), ("d", C.c_ubyte * 8)]

    class Value(C.Union):
        _fields_ = [("integer", C.c_longlong), ("pointer", C.c_void_p), ("boolean", C.c_short), ("record", C.c_void_p * 2)]

    class Variant(C.Structure):
        _fields_ = [("vt", C.c_ushort), ("r1", C.c_ushort), ("r2", C.c_ushort), ("r3", C.c_ushort), ("value", Value)]

    class Params(C.Structure):
        _fields_ = [("values", C.POINTER(Variant)), ("named", C.POINTER(DISPID)), ("count", C.c_uint), ("named_count", C.c_uint)]

    class ExceptionInfo(C.Structure):
        _fields_ = [("code", C.c_ushort), ("reserved", C.c_ushort), ("source", C.c_void_p), ("description", C.c_void_p), ("help", C.c_void_p), ("context", DWORD), ("reserved_pointer", C.c_void_p), ("deferred", C.c_void_p), ("status", HRESULT)]

    ole32.CLSIDFromString.argtypes = [C.c_wchar_p, C.POINTER(GUID)]
    ole32.CLSIDFromProgID.argtypes = [C.c_wchar_p, C.POINTER(GUID)]
    ole32.CoCreateInstance.argtypes = [C.POINTER(GUID), C.c_void_p, DWORD, C.POINTER(GUID), C.POINTER(C.c_void_p)]
    oleaut.SysAllocString.argtypes, oleaut.SysAllocString.restype = [C.c_wchar_p], C.c_void_p
    oleaut.SysFreeString.argtypes = [C.c_void_p]
    oleaut.SysFreeString.restype = None
    oleaut.VariantClear.argtypes = [C.POINTER(Variant)]
    null_guid, dispatch_guid = GUID(), GUID()
    ole32.CLSIDFromString("{00020400-0000-0000-C000-000000000046}", C.byref(dispatch_guid))
    initialized = False
    objects = []

    class Dispatch:
        def __init__(self, pointer):
            self.pointer = C.c_void_p(pointer)
            self.vtable = C.cast(self.pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
            objects.append(self)

        def invoke(self, name, *arguments, flags=1):
            names = (C.c_wchar_p * 1)(name)
            identifier = DISPID()
            get_ids = C.WINFUNCTYPE(HRESULT, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_wchar_p), C.c_uint, DWORD, C.POINTER(DISPID))(self.vtable[5])
            result = get_ids(self.pointer, C.byref(null_guid), names, 1, 0, C.byref(identifier))
            if result < 0:
                raise OSError(f"SAPI member unavailable: {name} (HRESULT {result:#x})")
            values = (Variant * len(arguments))()
            strings = []
            for index, argument in enumerate(reversed(arguments)):
                value = values[index]
                if isinstance(argument, Dispatch):
                    value.vt, value.value.pointer = 9, argument.pointer.value
                elif type(argument) is bool:
                    value.vt, value.value.boolean = 11, -1 if argument else 0
                elif type(argument) is int:
                    value.vt, value.value.integer = 3, argument
                else:
                    pointer = oleaut.SysAllocString(str(argument))
                    strings.append(pointer)
                    value.vt, value.value.pointer = 8, pointer
            named_id = DISPID(-3)
            params = Params(values, C.pointer(named_id) if flags in (4, 8) else None, len(arguments), 1 if flags in (4, 8) else 0)
            answer, error_info, bad_argument = Variant(), ExceptionInfo(), C.c_uint()
            invoke = C.WINFUNCTYPE(HRESULT, C.c_void_p, DISPID, C.POINTER(GUID), DWORD, C.c_ushort, C.POINTER(Params), C.POINTER(Variant), C.POINTER(ExceptionInfo), C.POINTER(C.c_uint))(self.vtable[6])
            try:
                result = invoke(self.pointer, identifier, C.byref(null_guid), 0, flags, C.byref(params), C.byref(answer), C.byref(error_info), C.byref(bad_argument))
                if result < 0:
                    if error_info.deferred:
                        C.WINFUNCTYPE(HRESULT, C.POINTER(ExceptionInfo))(error_info.deferred)(C.byref(error_info))
                    detail = C.wstring_at(error_info.description) if error_info.description else f"HRESULT {result:#x}, SAPI status {error_info.status:#x}, argument {bad_argument.value}"
                    if error_info.status == -2147200960:
                        detail += "; the current account cannot access the installed voice registry; use an account with that voice or reuse the prepared WAV files, without changing system settings"
                    raise OSError(f"SAPI {name}: {detail}")
                if answer.vt == 9:
                    pointer = answer.value.pointer
                    answer.vt = 0  # Transfer the returned COM reference to Dispatch.
                    return Dispatch(pointer)
                if answer.vt == 8:
                    return C.wstring_at(answer.value.pointer)
                if answer.vt in (2, 3, 19):
                    return int(answer.value.integer)
                return None
            finally:
                oleaut.VariantClear(C.byref(answer))
                for pointer in strings:
                    oleaut.SysFreeString(pointer)
                for pointer in (error_info.source, error_info.description, error_info.help):
                    if pointer:
                        oleaut.SysFreeString(pointer)

        def close(self):
            if self.pointer:
                C.WINFUNCTYPE(DWORD, C.c_void_p)(self.vtable[2])(self.pointer)
                self.pointer = C.c_void_p()

    def create(name):
        class_id, pointer = GUID(), C.c_void_p()
        ole32.CLSIDFromProgID(name, C.byref(class_id))
        ole32.CoCreateInstance(C.byref(class_id), None, 1, C.byref(dispatch_guid), C.byref(pointer))
        return Dispatch(pointer.value)

    try:
        ole32.CoInitialize(None)
        initialized = True
        voice = create("SAPI.SpVoice")
        voices = voice.invoke("GetVoices", "Language=804")
        if not voices.invoke("Count", flags=2):
            raise OSError("No installed Simplified Chinese SAPI voice; reuse the provided demo WAV files")
        token = voices.invoke("Item", 0)
        voice.invoke("Voice", token, flags=8)
        voice.invoke("Rate", 1, flags=4)
        for unit in document["units"]:
            for index, content in enumerate(unit["lines"], 1):
                path = (assets / f"{unit['id']}-{index}.wav").resolve()
                if path.is_file() and not replace:
                    try:
                        with wave.open(str(path), "rb") as existing:
                            if existing.getnframes() > 0:
                                continue
                    except (wave.Error, EOFError) as error:
                        print(f"Regenerating incomplete demo audio {path.name}: {error}", flush=True)
                stream = create("SAPI.SpFileStream")
                opened = False
                try:
                    stream.invoke("Open", str(path), 3, False)
                    opened = True
                    voice.invoke("AudioOutputStream", stream, flags=8)
                    voice.invoke("Speak", content, 0)
                finally:
                    if opened:
                        stream.invoke("Close")
                    stream.close()
                print(f"Synthesized local demo voice: {path.name}", flush=True)
    finally:
        for item in reversed(objects):
            item.close()
        if initialized:
            ole32.CoUninitialize()
