#!/usr/bin/env python3
"""
Find & Replace Tool cho thư mục truyen/translated

Hỗ trợ:
- Thay thế text thông thường
- Regex
- Không phân biệt hoa/thường
- Preview trước khi thay
- Backup
- Batch nhiều cặp thay thế
- Chọn file bằng pattern
- Ký tự đặc biệt trong REPLACE:
    \\n  -> xuống dòng
    \\n\\n -> xuống 2 dòng
    \\t  -> tab
"""

import os
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime


# ── ANSI colors ──────────────────────────────────────────────────────────────

RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"


# ── Paths ─────────────────────────────────────────────────────────────────────

DICH_DIR = Path(__file__).parent / "truyen" / "OJE" / "translated"
BACKUP_DIR = Path(__file__).parent / "truyen" / "OJE" / "_backup"

print(f"{DIM}💾  dich_dir directory: {DICH_DIR}{RESET}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗
║        🔍  Find & Replace — truyen/translated        ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def parse_special_chars(text: str) -> str:
    """
    Chuyển các ký hiệu đặc biệt trong REPLACE thành ký tự thật.

    Hỗ trợ:
        \\n  -> xuống dòng
        \\r  -> carriage return
        \\t  -> tab
        \\\\  -> dấu backslash

    Ví dụ:
        .\\n"
    sẽ trở thành:
        .
        "

    Có thể dùng:
        \\n\\n
        \\n\\n\\n
    để xuống nhiều dòng.
    """

    result = []
    i = 0

    escape_map = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "\\": "\\",
    }

    while i < len(text):

        if text[i] == "\\" and i + 1 < len(text):
            next_char = text[i + 1]

            if next_char in escape_map:
                result.append(escape_map[next_char])
                i += 2
                continue

            # Giữ nguyên escape không nhận diện.
            # Quan trọng khi dùng regex như \1, \2, \g<1>...
            result.append("\\")
            result.append(next_char)
            i += 2
            continue

        result.append(text[i])
        i += 1

    return "".join(result)


def display_special_chars(text: str) -> str:
    """
    Hiển thị ký tự xuống dòng/tab dưới dạng \\n, \\t
    để preview dễ đọc hơn.
    """

    return (
        text
        .replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def make_backup(files: list[Path]):
    """
    Tạo backup các file trước khi chỉnh sửa.
    """

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = BACKUP_DIR / ts

    bk.mkdir(parents=True, exist_ok=True)

    for f in files:
        shutil.copy2(f, bk / f.name)

    print(f"{DIM}💾  Backup saved → {bk}{RESET}")

    return bk


# ── Find & Replace ────────────────────────────────────────────────────────────

def find_and_replace(
    find: str,
    replace: str,
    use_regex: bool = False,
    case_sensitive: bool = True,
    file_pattern: str = "*.md",
    dry_run: bool = False,
    interactive: bool = False,
    backup: bool = True,
):
    flags = 0 if case_sensitive else re.IGNORECASE

    # ── Collect matching files ────────────────────────────────────────────────

    all_files = sorted(DICH_DIR.glob(file_pattern))

    if not all_files:
        print(
            f"{YELLOW}"
            f"⚠  Không tìm thấy file nào khớp với pattern "
            f"'{file_pattern}'"
            f"{RESET}"
        )
        return

    # ── First pass: tìm match ─────────────────────────────────────────────────

    hits: dict[Path, list[tuple[int, str, str]]] = {}

    total_occurrences = 0

    for fp in all_files:

        text = fp.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)

        file_hits = []

        for i, line in enumerate(lines, 1):

            if use_regex:

                matches = list(
                    re.finditer(
                        find,
                        line,
                        flags=flags
                    )
                )

                if not matches:
                    continue

                total_occurrences += len(matches)

                new_line = re.sub(
                    find,
                    replace,
                    line,
                    flags=flags
                )

            else:

                if case_sensitive:

                    count = line.count(find)

                    if count == 0:
                        continue

                    total_occurrences += count

                    new_line = line.replace(
                        find,
                        replace
                    )

                else:

                    matches = list(
                        re.finditer(
                            re.escape(find),
                            line,
                            flags=re.IGNORECASE
                        )
                    )

                    if not matches:
                        continue

                    total_occurrences += len(matches)

                    new_line = re.sub(
                        re.escape(find),
                        lambda _: replace,
                        line,
                        flags=re.IGNORECASE
                    )

            if new_line != line:

                file_hits.append(
                    (
                        i,
                        line.rstrip("\r\n"),
                        new_line.rstrip("\r\n")
                    )
                )

        if file_hits:
            hits[fp] = file_hits

    # ── Không tìm thấy ────────────────────────────────────────────────────────

    if not hits:
        print(
            f"{YELLOW}"
            f"🔍  Không tìm thấy '{find}' trong bất kỳ file nào."
            f"{RESET}"
        )
        return

    # ── Summary ───────────────────────────────────────────────────────────────

    print(
        f"{GREEN}{BOLD}"
        f"Tìm thấy {total_occurrences} lần xuất hiện "
        f"trong {len(hits)} file:"
        f"{RESET}\n"
    )

    print(
        f"{DIM}"
        f"Find    : {display_special_chars(find)}"
        f"{RESET}"
    )

    print(
        f"{DIM}"
        f"Replace : {display_special_chars(replace)}"
        f"{RESET}\n"
    )

    # ── Preview ───────────────────────────────────────────────────────────────

    for fp, file_hits in hits.items():

        print(
            f"  {CYAN}{fp.name}{RESET}"
            f"  ({len(file_hits)} dòng)"
        )

        for lineno, old, new in file_hits[:5]:

            print(
                f"    {DIM}L{lineno:<4}{RESET} "
                f"{RED}- {old}{RESET}"
            )

            # Replacement có thể chứa newline
            new_parts = new.splitlines()

            if not new_parts:
                new_parts = [""]

            for j, part in enumerate(new_parts):

                prefix = (
                    f"L{lineno:<4}"
                    if j == 0
                    else "     "
                )

                print(
                    f"    {DIM}{prefix}{RESET} "
                    f"{GREEN}+ {part}{RESET}"
                )

        if len(file_hits) > 5:

            print(
                f"    {DIM}"
                f"… và {len(file_hits) - 5} dòng nữa"
                f"{RESET}"
            )

        print()

    # ── Dry run ───────────────────────────────────────────────────────────────

    if dry_run:

        print(
            f"{YELLOW}"
            f"[Dry-run] Không thay đổi file nào."
            f"{RESET}"
        )

        return

    # ── Confirm ───────────────────────────────────────────────────────────────

    if interactive:

        ans = input(
            f"{BOLD}"
            f"Tiến hành thay thế? [y/N] "
            f"{RESET}"
        ).strip().lower()

        if ans != "y":
            print("Hủy.")
            return

    # ── Backup ────────────────────────────────────────────────────────────────

    if backup:
        make_backup(list(hits.keys()))

    # ── Apply ─────────────────────────────────────────────────────────────────

    changed = 0

    for fp in hits:

        text = fp.read_text(encoding="utf-8")

        if use_regex:

            new_text = re.sub(
                find,
                replace,
                text,
                flags=flags
            )

        else:

            if case_sensitive:

                new_text = text.replace(
                    find,
                    replace
                )

            else:

                new_text = re.sub(
                    re.escape(find),
                    lambda _: replace,
                    text,
                    flags=re.IGNORECASE
                )

        fp.write_text(
            new_text,
            encoding="utf-8"
        )

        changed += 1

    print(
        f"{GREEN}{BOLD}"
        f"✅  Đã cập nhật {changed} file "
        f"({total_occurrences} lần thay thế)."
        f"{RESET}"
    )


# ── Interactive mode ──────────────────────────────────────────────────────────

def interactive_mode():

    banner()

    print(
        f"{BOLD}"
        f"Chế độ: Tương tác"
        f"{RESET}\n"
    )

    print(
        f"{DIM}"
        "REPLACE hỗ trợ ký tự đặc biệt:\n"
        r"  \n   = xuống dòng" "\n"
        r"  \n\n = xuống 2 dòng" "\n"
        r"  \t   = tab" "\n"
        f"{RESET}"
    )

    find_text = input(
        f"{CYAN}Tìm (find)    : {RESET}"
    )

    replace_input = input(
        f"{GREEN}Thay (replace): {RESET}"
    )

    # Chuyển \n thành newline thật
    replace_text = parse_special_chars(
        replace_input
    )

    use_regex = (
        input("Dùng regex? [y/N]: ")
        .strip()
        .lower()
        == "y"
    )

    case_sens = (
        input("Phân biệt hoa/thường? [Y/n]: ")
        .strip()
        .lower()
        != "n"
    )

    pattern = (
        input("File pattern [*.md]: ")
        .strip()
        or "*.md"
    )

    do_backup = (
        input("Tạo backup? [Y/n]: ")
        .strip()
        .lower()
        != "n"
    )

    print()

    find_and_replace(
        find=find_text,
        replace=replace_text,
        use_regex=use_regex,
        case_sensitive=case_sens,
        file_pattern=pattern,
        dry_run=False,
        interactive=True,
        backup=do_backup,
    )


# ── Batch mode ────────────────────────────────────────────────────────────────

def batch_mode(pairs_file: str):
    """
    File format:

        FIND: <text>
        REPLACE: <text>
        REGEX: false
        ---

    Ví dụ:

        FIND: . "
        REPLACE: .\\n"
        REGEX: false
        ---
    """

    banner()

    p = Path(pairs_file)

    if not p.exists():

        print(
            f"{RED}"
            f"File không tồn tại: {p}"
            f"{RESET}"
        )

        sys.exit(1)

    content = p.read_text(
        encoding="utf-8"
    )

    pairs = []

    for block in content.split("---"):

        block = block.strip()

        if not block:
            continue

        find_m = re.search(
            r"^FIND:\s*(.+)$",
            block,
            re.MULTILINE
        )

        replace_m = re.search(
            r"^REPLACE:\s*(.*)$",
            block,
            re.MULTILINE
        )

        regex_m = re.search(
            r"^REGEX:\s*(true|false)$",
            block,
            re.MULTILINE | re.IGNORECASE
        )

        if find_m:

            raw_replace = (
                replace_m.group(1)
                if replace_m
                else ""
            )

            pairs.append({
                "find": find_m.group(1),
                "replace": parse_special_chars(
                    raw_replace
                ),
                "regex": (
                    regex_m.group(1).lower() == "true"
                    if regex_m
                    else False
                ),
            })

    if not pairs:

        print(
            f"{YELLOW}"
            f"Không tìm thấy cặp nào trong file batch."
            f"{RESET}"
        )

        return

    print(
        f"{BOLD}"
        f"Batch: {len(pairs)} cặp thay thế"
        f"{RESET}\n"
    )

    for i, pair in enumerate(pairs, 1):

        print(
            f"{CYAN}[{i}/{len(pairs)}] "
            f"{BOLD}"
            f"{display_special_chars(pair['find'])}"
            f"{RESET}"
            f" → "
            f"{GREEN}"
            f"{display_special_chars(pair['replace'])}"
            f"{RESET}"
        )

        find_and_replace(
            find=pair["find"],
            replace=pair["replace"],
            use_regex=pair["regex"],
            dry_run=False,
            interactive=False,
            backup=(i == 1),
        )

        print()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():

    parser = argparse.ArgumentParser(
        description="Find & Replace trong truyen/translated",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=r"""
Ví dụ:

  Interactive:
      python replace.py --interactive

  Thay ". \"" thành xuống dòng:
      FIND    : . "
      REPLACE : .\n"

  Xuống 2 dòng:
      REPLACE : .\n\n"

  Dry run:
      python replace.py '. "' '.\n"' --dry-run
"""
    )

    parser.add_argument(
        "find",
        nargs="?",
        help="Chuỗi cần tìm"
    )

    parser.add_argument(
        "replace",
        nargs="?",
        default="",
        help=r"Chuỗi thay thế. Hỗ trợ \n, \t..."
    )

    parser.add_argument(
        "-r",
        "--regex",
        action="store_true",
        help="Dùng biểu thức chính quy"
    )

    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="Không phân biệt hoa/thường"
    )

    parser.add_argument(
        "-p",
        "--pattern",
        default="*.md",
        help="Pattern file (mặc định: *.md)"
    )

    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Chỉ xem trước, không thay đổi"
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Không tạo backup"
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Chế độ tương tác"
    )

    parser.add_argument(
        "--batch",
        metavar="FILE",
        help="File batch chứa nhiều cặp thay thế"
    )

    args = parser.parse_args()

    # Enable ANSI colors on Windows
    if sys.platform == "win32":
        os.system("")

    if args.batch:

        batch_mode(
            args.batch
        )

    elif args.interactive or not args.find:

        interactive_mode()

    else:

        banner()

        replace_text = parse_special_chars(
            args.replace
        )

        find_and_replace(
            find=args.find,
            replace=replace_text,
            use_regex=args.regex,
            case_sensitive=not args.ignore_case,
            file_pattern=args.pattern,
            dry_run=args.dry_run,
            interactive=not args.dry_run,
            backup=not args.no_backup,
        )


if __name__ == "__main__":
    main()