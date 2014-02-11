import sys


class DisabledStderr():
    def __enter__(self):
        self.stderr = sys.stderr
        sys.stderr = None
    
    def __exit__(self, type, value, traceback):
        sys.stderr = self.stderr


class ZeroDefaultDict(dict):
    def __getitem__(self, key):
        return self.get(key, 0)
