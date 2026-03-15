from pathlib import Path
import sys


def load_names(path: str) -> list[str]:
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def greet(name: str) -> str:
    return f"Hello, {name.strip()}!"


def main() -> None:
    source = sys.argv[1]
    for name in load_names(source):
        print(greet(name))


if __name__ == "__main__":
    main()
