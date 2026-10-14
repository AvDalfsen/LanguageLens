"""Terminate native helper children when their owning worker exits on Windows."""
import ctypes
import os
from ctypes import wintypes


class ChildOwnership:
    def __init__(self,process_handle):
        from ctypes import windll
        self.kernel=windll.kernel32
        class Basic(ctypes.Structure):
            _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),
                ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),
                ('ActiveProcessLimit',wintypes.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
        class IO(ctypes.Structure):_fields_=[(n,ctypes.c_ulonglong) for n in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
        class Extended(ctypes.Structure):_fields_=[('BasicLimitInformation',Basic),('IoInfo',IO),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
        self.kernel.CreateJobObjectW.restype=wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        info=Extended();info.BasicLimitInformation.LimitFlags=0x2000
        if (not self.handle or not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info))
                or not self.kernel.AssignProcessToJobObject(self.handle,int(process_handle))):
            self.close();raise OSError('Could not supervise local translation helper.')
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


def own_child(process):
    if os.name!='nt':return None
    try:return ChildOwnership(process._handle)
    except OSError:
        process.kill();process.wait();raise


def own_pid(pid):
    """Own the real worker, including Windows venv redirector descendants."""
    if os.name!='nt':return None
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x0101,False,pid)  # SET_QUOTA | TERMINATE
    if not handle:raise OSError('Could not supervise local translation worker.')
    try:return ChildOwnership(handle)
    finally:kernel.CloseHandle(handle)
