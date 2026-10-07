"""Run: python3 test_widget.py (requires a GUI session and Tk >= 8.6)."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    child = '''
from unittest.mock import patch
import widget
assert widget.tk.TkVersion >= 8.6, 'Use Tk >= 8.6; system Tk 8.5 rendered blank on the tested Mac'

checks = []
def run_briefly(self):
    def verify():
        try:
            assert self.root.winfo_exists()
            assert self.root.winfo_viewable(), 'Window is not mapped'
            assert not self.root.overrideredirect(), 'Keep the native title bar'
            assert self._rows, 'No scan result rendered'
            checks.append(True)
        finally:
            self._quit()
    self.root.after(3000, verify)
    self.root.mainloop()

with patch.object(widget.tk, 'Tk', wraps=widget.tk.Tk) as create_root, \\
     patch.object(widget.FloatWidget, 'run', run_briefly):
    widget.main()
    assert checks == [True]
    assert create_root.call_count == 1, 'Startup must use exactly one Tk root'
print('PASS: launch entry, single Tk root, rendering, refresh and shutdown')
'''
    result = subprocess.run([sys.executable, "-c", child], cwd=Path(__file__).resolve().parent,
                            capture_output=True, text=True, timeout=15,
                            env={**os.environ, "TK_SILENCE_DEPRECATION": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert not result.stderr.strip(), result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
