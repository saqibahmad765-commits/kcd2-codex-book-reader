"""Bind automatic speech startup to one Windows game-process handle."""
import ctypes
from ctypes import wintypes

class GameLifetime:
    def __init__(self, pid):
        if not isinstance(pid,int) or isinstance(pid,bool) or not 0 < pid <= 0xffffffff:
            raise ValueError('Invalid game process ID')
        self.api = ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.OpenProcess(0x00100000,False,pid) # SYNCHRONIZE only
        if not self.handle:
            raise OSError(ctypes.get_last_error(),'Could not watch the launching game process')

    def alive(self):
        result = self.api.WaitForSingleObject(self.handle,0)
        if result == 258: # WAIT_TIMEOUT: process has not exited
            return True
        if result == 0:
            return False
        raise OSError(ctypes.get_last_error(),'Game-process wait failed')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
