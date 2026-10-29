"""Read-only XInput; never injects or consumes a game's button input."""
import ctypes
from ctypes import wintypes

class Gamepad(ctypes.Structure):
    _fields_ = [('buttons', wintypes.WORD), ('leftTrigger', ctypes.c_ubyte),
                ('rightTrigger', ctypes.c_ubyte), ('lx', ctypes.c_short),
                ('ly', ctypes.c_short), ('rx', ctypes.c_short), ('ry', ctypes.c_short)]

class State(ctypes.Structure):
    _fields_ = [('packet', wintypes.DWORD), ('gamepad', Gamepad)]

class Hold:
    def __init__(self, seconds=0.8):
        self.seconds, self.started, self.fired = seconds, None, False

    def update(self, pressed, now):
        if not pressed:
            self.started, self.fired = None, False
            return False
        if self.started is None:
            self.started = now
        if not self.fired and now - self.started >= self.seconds:
            self.fired = True
            return True
        return False

class Controller:
    def __init__(self):
        self.xinput = ctypes.WinDLL('xinput1_4')
        self.xinput.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(State)]
        self.user = ctypes.WinDLL('user32')
        self.kernel = ctypes.WinDLL('kernel32')
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    def foreground_game(self):
        window = self.user.GetForegroundWindow()
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            buffer = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(buffer))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return False
            return buffer.value.lower().startswith('e:\\steamlibrary\\steamapps\\common\\kingdomcomedeliverance2\\')
        finally:
            self.kernel.CloseHandle(handle)

    def snapshot(self):
        connected, pressed = [], False
        for slot in range(4):
            state = State()
            if self.xinput.XInputGetState(slot, ctypes.byref(state)) == 0:
                connected.append(slot)
                pressed = pressed or bool(state.gamepad.buttons & 0x8000)
        return tuple(connected), pressed

    def y_pressed(self):
        return self.snapshot()[1]
