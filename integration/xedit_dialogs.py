"""Narrow Windows handling for xEdit's documented full-module selection dialog."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import threading


class ModuleSelectionWatcher:
    def __init__(self, task, process, expected_count, progress_file=None):
        self.task = Path(task)
        self.process = process
        self.expected_count = expected_count
        self.progress_file = Path(progress_file) if progress_file else None
        self.stopped = threading.Event()
        self.sent = False
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()

    def watch(self):
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        user.IsWindowVisible.restype = wintypes.BOOL
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.PostMessageW.restype = wintypes.BOOL

        def text(handle, class_name=False):
            value = ctypes.create_unicode_buffer(512)
            (user.GetClassNameW if class_name else user.GetWindowTextW)(handle, value, len(value))
            return value.value

        def find_dialog():
            matches = []
            def top(handle, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value == self.process.pid and text(handle, True) == 'TfrmModuleSelect' and text(handle) == 'Module Selection' and user.IsWindowVisible(handle):
                    matches.append(handle)
                return True
            user.EnumWindows(callback_type(top), 0)
            return matches

        def main_window():
            found = []
            def top(handle, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value == self.process.pid and text(handle, True) == 'TfrmMain' and user.IsWindowVisible(handle) and user.IsWindowEnabled(handle):
                    found.append(handle)
                return True
            user.EnumWindows(callback_type(top), 0)
            return found[0] if len(found) == 1 else None

        def blocking_dialog():
            found = []
            def top(handle, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value == self.process.pid and text(handle, True) in ('TfrmModuleSelect', 'TfrmFileSelect', '#32770') and user.IsWindowVisible(handle):
                    found.append(handle)
                return True
            user.EnumWindows(callback_type(top), 0)
            return found

        try:
            script_started = False
            shutdown_sent = False
            while not self.stopped.wait(0.5) and self.process.poll() is None and not shutdown_sent:
                dialogs = find_dialog()
                if len(dialogs) == 1 and not self.sent:
                    buttons = []
                    def child(handle, _):
                        if text(handle, True) == 'TButton' and text(handle) == 'OK' and user.IsWindowVisible(handle):
                            buttons.append(handle)
                        return True
                    user.EnumChildWindows(dialogs[0], callback_type(child), 0)
                    if len(buttons) == 1:
                        self.sent = True
                        receipt = {'utc': datetime.now(timezone.utc).isoformat(), 'process_id': self.process.pid,
                                   'dialog_class': 'TfrmModuleSelect', 'dialog_title': 'Module Selection',
                                   'action': 'PostMessage BM_CLICK to the sole visible OK button once',
                                   'expected_plugin_count': self.expected_count,
                                   'required_gate': 'Native Background Loader plugin sequence must exactly equal input_inventory.json plus the xEdit pseudo-plugin; this click alone is not acceptance',
                                   'game_launched': False}
                        if not user.PostMessageW(buttons[0], 0x00F5, 0, 0):
                            raise ctypes.WinError(ctypes.get_last_error())
                        (self.task / 'module_selection_confirmation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
                main = main_window()
                if main:
                    title = text(main)
                    if ('[Applying script "' in title and f'"{self.task.name}"' in title) or (self.progress_file is not None and self.progress_file.is_file()):
                        script_started = True
                    if script_started and title == 'SSEScript 4.1.5f x64' and not blocking_dialog():
                        shutdown_sent = True
                        if not user.PostMessageW(main, 0x0010, 0, 0):
                            raise ctypes.WinError(ctypes.get_last_error())
                        receipt = {'process_id': self.process.pid, 'action': 'One normal WM_CLOSE after intended script title completed',
                                   'forced_termination': False, 'dialogs_approved_after_script': False,
                                   'required_gate': 'Exit zero, exact native plugin sequence, log markers and required candidate must pass'}
                        (self.task / 'shutdown_request.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        except BaseException as exc:
            (self.task / 'module_selection_error.json').write_text(json.dumps({'error': repr(exc)}, indent=2) + '\n', encoding='utf-8')

    def stop(self):
        self.stopped.set()
        self.thread.join(timeout=2)
