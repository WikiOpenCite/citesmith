from pathlib import Path
from urllib.parse import urlparse


def derive_temp_paths(file_url: str, output_dir: Path) -> tuple[Path, Path, Path]:
    """Compute temporary output file paths for authors, institutions, and works.

    Args:
        file_url (str): URL of the OpenAlex data file.
        output_dir (Path): Directory where temporary files will be written.

    Returns:
        tuple[Path, Path, Path]: Paths for authors, institutions, and works temporary files.
    """
    parsed_url = urlparse(file_url)
    original_name = Path(parsed_url.path).name
    if not original_name:
        original_name = "openalex-file.jsonl.gz"

    stem = (
        original_name.rsplit(".gz", 1)[0]
        if original_name.endswith(".gz")
        else original_name
    )
    path_parts = [part for part in parsed_url.path.strip("/").split("/") if part]

    date_value = None
    part_value = None
    for path_part in path_parts:
        if path_part.startswith("updated_date="):
            date_value = path_part.split("=", 1)[1]
        elif path_part.startswith("part_"):
            part_value = path_part.rsplit(".", 1)[0]

    filename_parts = [stem]
    if date_value:
        filename_parts.append(f"updated_date={date_value}")
    if part_value:
        filename_parts.append(part_value)

    safe_stem = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in "-".join(filename_parts)
    )
    authors_path = output_dir / f"{safe_stem}.authors"
    institutions_path = output_dir / f"{safe_stem}.institutions"
    works_path = output_dir / f"{safe_stem}.works"
    return authors_path, institutions_path, works_path
