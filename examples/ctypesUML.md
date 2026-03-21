# ctypes Mardown UML Class Diagram

```mermaid
classDiagram
namespace ctypes{
  class ctypes__endian
  class ctypes_wintypes
  class ctypes_CDLL["CDLL"] {
    -_FuncPtr: None
    -_func_flags_
    -_func_restype_
    -_handle: int
    -_name: str
  }
  class ctypes_CDLL__FuncPtr["CDLL._FuncPtr"] {
    -_flags_
    -_restype_
  }
  class ctypes_CFunctionType["CFunctionType"] {
    -_argtypes_
    -_flags_
    -_restype_
  }
  class ctypes_HRESULT["HRESULT"] {
    -_check_retval_
    -_type_: str
  }
  class ctypes_LibraryLoader["LibraryLoader"] {
    -__class_getitem__: classmethod
    -_dlltype
    +LoadLibrary(name)
  }
  class ctypes_OleDLL["OleDLL"] {
    -_func_flags_
    -_func_restype_
  }
  class ctypes_PyDLL["PyDLL"] {
    -_func_flags_
  }
  class ctypes_WinDLL["WinDLL"] {
    -_func_flags_
  }
  class ctypes_WinFunctionType["WinFunctionType"] {
    -_argtypes_
    -_flags_
    -_restype_
  }
  class ctypes_c_bool["c_bool"] {
    -_type_: str
  }
  class ctypes_c_byte["c_byte"] {
    -_type_: str
  }
  class ctypes_c_char["c_char"] {
    -_type_: str
  }
  class ctypes_c_char_p["c_char_p"] {
    -_type_: str
  }
  class ctypes_c_double["c_double"] {
    -_type_: str
  }
  class ctypes_c_float["c_float"] {
    -_type_: str
  }
  class ctypes_c_int["c_int"] {
    -_type_: str
  }
  class ctypes_c_long["c_long"] {
    -_type_: str
  }
  class ctypes_c_longdouble["c_longdouble"] {
    -_type_: str
  }
  class ctypes_c_longlong["c_longlong"] {
    -_type_: str
  }
  class ctypes_c_short["c_short"] {
    -_type_: str
  }
  class ctypes_c_ubyte["c_ubyte"] {
    -_type_: str
  }
  class ctypes_c_uint["c_uint"] {
    -_type_: str
  }
  class ctypes_c_ulong["c_ulong"] {
    -_type_: str
  }
  class ctypes_c_ulonglong["c_ulonglong"] {
    -_type_: str
  }
  class ctypes_c_ushort["c_ushort"] {
    -_type_: str
  }
  class ctypes_c_void_p["c_void_p"] {
    -_type_: str
  }
  class ctypes_c_wchar["c_wchar"] {
    -_type_: str
  }
  class ctypes_c_wchar_p["c_wchar_p"] {
    -_type_: str
  }
  class ctypes_py_object["py_object"] {
    -_type_: str
  }
}
namespace ctypes__endian{
  class ctypes__endian_BigEndianStructure["BigEndianStructure"] {
    -__slots__: tuple
    -_swappedbytes_: None
  }
  class ctypes__endian_BigEndianUnion["BigEndianUnion"] {
    -__slots__: tuple
    -_swappedbytes_: None
  }
  class ctypes__endian_LittleEndianStructure["LittleEndianStructure"] {
    -__slots__: tuple
    -_swappedbytes_: None
  }
  class ctypes__endian_LittleEndianUnion["LittleEndianUnion"] {
    -__slots__: tuple
    -_swappedbytes_: None
  }
  class ctypes__endian__swapped_meta["_swapped_meta"] {
  }
  class ctypes__endian__swapped_struct_meta["_swapped_struct_meta"] {
  }
  class ctypes__endian__swapped_union_meta["_swapped_union_meta"] {
  }
}
namespace ctypes_wintypes{
  class ctypes_wintypes_FILETIME["FILETIME"] {
    -_fields_: list
  }
  class ctypes_wintypes_MSG["MSG"] {
    -_fields_: list
  }
  class ctypes_wintypes_POINT["POINT"] {
    -_fields_: list
  }
  class ctypes_wintypes_RECT["RECT"] {
    -_fields_: list
  }
  class ctypes_wintypes_SIZE["SIZE"] {
    -_fields_: list
  }
  class ctypes_wintypes_VARIANT_BOOL["VARIANT_BOOL"] {
    -_type_: str
  }
  class ctypes_wintypes_WIN32_FIND_DATAA["WIN32_FIND_DATAA"] {
    -_fields_: list
  }
  class ctypes_wintypes_WIN32_FIND_DATAW["WIN32_FIND_DATAW"] {
    -_fields_: list
  }
  class ctypes_wintypes__COORD["_COORD"] {
    -_fields_: list
  }
  class ctypes_wintypes__SMALL_RECT["_SMALL_RECT"] {
    -_fields_: list
  }
}

ctypes_CDLL <|-- ctypes_OleDLL
ctypes_CDLL <|-- ctypes_PyDLL
ctypes_CDLL <|-- ctypes_WinDLL
ctypes__endian__swapped_meta <|-- ctypes__endian__swapped_struct_meta
ctypes__endian__swapped_meta <|-- ctypes__endian__swapped_union_meta
```
