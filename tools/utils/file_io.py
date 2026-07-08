import os


def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()


def write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
