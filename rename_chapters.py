"""Rename chapter files to ``v1_c<zero-based chapter>_s1.md``.

Supported input names include:

* ``001 - Chapter 1 Prologue.txt`` -> ``v1_c0_s1.md``
* ``002 - Chapter 2 Azriel Crimson.txt`` -> ``v1_c1_s1.md``
* ``Chapter_0418_The_Beginning_of_the_End.md`` -> ``v1_c417_s1.md``

This script only renames files. It never reads or modifies their contents.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DIRECTORY = Path(__file__).resolve().parent / "truyen" / "geoyv" / "raw"
SUPPORTED_EXTENSIONS = {".txt", ".md"}
NAME_PATTERNS = (
    re.compile(r"^\d+\s*-\s*Chapter\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"^Chapter_(\d+)(?:_|$)", re.IGNORECASE),
    # Makes the script idempotent and also converts an existing .txt target to .md.
    re.compile(r"^v1_c(\d+)_s1$", re.IGNORECASE),
)


@dataclass(frozen=True)
class RenameOperation:
    source: Path
    destination: Path


def chapter_index(path: Path) -> int | None:
    """Return the zero-based chapter index encoded in a supported file name."""
    for pattern_index, pattern in enumerate(NAME_PATTERNS):
        match = pattern.match(path.stem)
        if not match:
            continue

        number = int(match.group(1))
        if pattern_index == 2:
            return number
        if number < 1:
            raise ValueError(f"Số chương phải lớn hơn 0: {path.name}")
        return number - 1
    return None


def build_plan(directory: Path) -> tuple[list[RenameOperation], list[Path]]:
    """Build and validate the complete rename plan before changing anything."""
    operations: list[RenameOperation] = []
    skipped: list[Path] = []

    for source in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append(source)
            continue

        index = chapter_index(source)
        if index is None:
            skipped.append(source)
            continue

        destination = directory / f"v1_c{index}_s1.md"
        if source != destination:
            operations.append(RenameOperation(source, destination))

    destinations: dict[str, Path] = {}
    source_keys = {str(item.source.resolve()).casefold() for item in operations}
    for item in operations:
        key = str(item.destination.resolve()).casefold()
        previous = destinations.get(key)
        if previous is not None:
            raise FileExistsError(
                f"Hai file sẽ trùng tên đích {item.destination.name}: "
                f"{previous.name} và {item.source.name}"
            )
        destinations[key] = item.source

        if item.destination.exists() and key not in source_keys:
            raise FileExistsError(
                f"Tên đích đã tồn tại, không thể ghi đè: {item.destination}"
            )

    return operations, skipped


def execute_plan(operations: list[RenameOperation]) -> None:
    """Rename in two phases so source and destination names cannot collide."""
    staged: list[tuple[Path, Path]] = []
    try:
        for item in operations:
            temporary = item.source.with_name(f".__rename_{uuid.uuid4().hex}{item.source.suffix}")
            item.source.rename(temporary)
            staged.append((temporary, item.destination))

        for temporary, destination in staged:
            temporary.rename(destination)
    except Exception:
        # Best-effort rollback for files that are still using temporary names.
        original_by_destination = {item.destination: item.source for item in operations}
        for temporary, destination in reversed(staged):
            if temporary.exists():
                temporary.rename(original_by_destination[destination])
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Đổi tên file chương thành v1_cN_s1.md (N = số chương - 1)."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=DEFAULT_DIRECTORY,
        help=f"Thư mục cần xử lý (mặc định: {DEFAULT_DIRECTORY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ xem trước danh sách đổi tên, không sửa file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    directory = args.directory.expanduser().resolve()
    if not directory.is_dir():
        print(f"Lỗi: thư mục không tồn tại: {directory}", file=sys.stderr)
        return 1

    try:
        operations, skipped = build_plan(directory)
    except (OSError, ValueError) as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1

    if not operations:
        print("Không có file nào cần đổi tên.")
    else:
        for item in operations:
            print(f"{item.source.name} -> {item.destination.name}")

        if args.dry_run:
            print(f"\nXem trước: {len(operations)} file sẽ được đổi tên.")
        else:
            try:
                execute_plan(operations)
            except OSError as error:
                print(f"Lỗi khi đổi tên: {error}", file=sys.stderr)
                return 1
            print(f"\nĐã đổi tên {len(operations)} file.")

    if skipped:
        print(f"Bỏ qua {len(skipped)} mục không khớp định dạng hoặc không phải .txt/.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
