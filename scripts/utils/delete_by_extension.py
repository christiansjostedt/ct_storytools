import os
import sys
from pathlib import Path

def delete_files_by_extension_recursive(folder_path: str, extension: str) -> None:
    """
    Recursively delete all files with the specified extension in the given folder
    and all its subdirectories. Does NOT delete folders.
    """
    # Normalize extension
    ext = extension.strip().lower()
    if not ext.startswith('.'):
        ext = '.' + ext

    root_path = Path(folder_path).resolve()

    if not root_path.exists():
        print(f"Error: Path not found: {root_path}")
        return

    if not root_path.is_dir():
        print(f"Error: Not a directory: {root_path}")
        return

    print(f"\nSearching recursively for *{ext} files in:")
    print(f"  {root_path}\n")

    # Collect files first (much safer)
    files_to_delete = []

    for file_path in root_path.rglob(f"*{ext}"):
        if file_path.is_file():
            files_to_delete.append(file_path)

    if not files_to_delete:
        print(f"No .{ext[1:]} files found (recursive search).")
        return

    # Show preview
    print(f"Found {len(files_to_delete)} file(s):\n")
    for f in files_to_delete:
        try:
            rel_path = f.relative_to(root_path)
            print(f"  {rel_path}")
        except:
            print(f"  {f}")

    print(f"\nTotal: {len(files_to_delete)} files")

    # Confirmation
    confirm = input("\nPermanently delete these files? [y/N]: ").strip().lower()

    if confirm not in ('y', 'yes', 'ye'):
        print("Aborted. No files were deleted.")
        return

    # Delete
    deleted_count = 0
    errors = 0

    for file_path in files_to_delete:
        try:
            file_path.unlink()
            try:
                rel = file_path.relative_to(root_path)
                print(f"Deleted: {rel}")
            except:
                print(f"Deleted: {file_path.name}")
            deleted_count += 1
        except PermissionError:
            print(f"Permission denied: {file_path}")
            errors += 1
        except Exception as e:
            print(f"Error deleting {file_path}: {e}")
            errors += 1

    print(f"\nFinished:")
    print(f"  Successfully deleted: {deleted_count} file(s)")
    if errors:
        print(f"  Failed / skipped: {errors} file(s)")


def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print("  python delete_recursive.py <folder_path> <.extension>")
        print("Examples:")
        print("  python delete_recursive.py . png")
        print("  python delete_recursive.py ./photos jpg")
        print("  python delete_recursive.py \"C:\\Users\\You\\Downloads\" .webp")
        print("  python delete_recursive.py /home/user/projects/ .bak")
        sys.exit(1)

    folder = sys.argv[1]
    extension = sys.argv[2]

    delete_files_by_extension_recursive(folder, extension)


if __name__ == "__main__":
    main()