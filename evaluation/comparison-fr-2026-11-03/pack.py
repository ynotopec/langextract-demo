"""Package synthetic evidence compactly; leave raw files available locally."""

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    files = sorted((ROOT / "results").glob("*.json"))
    assert len(files) == 240, len(files)
    with (
        (ROOT / "responses.jsonl.gz").open("wb") as output,
        gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream,
    ):
        for file in files:
            row = {"file": file.name, **json.loads(file.read_text())}
            stream.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
    with (
        (ROOT / "pdfs.tar.gz").open("wb") as output,
        gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream,
        tarfile.open(fileobj=stream, mode="w") as archive,
    ):
        for file in sorted((ROOT / "pdfs").glob("*.pdf")):
            info = archive.gettarinfo(str(file), arcname="pdfs/" + file.name)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with file.open("rb") as source:
                archive.addfile(info, source)
    print(
        json.dumps(
            {
                "raw_response_files": len(files),
                "response_archive_bytes": (ROOT / "responses.jsonl.gz").stat().st_size,
                "pdf_archive_bytes": (ROOT / "pdfs.tar.gz").stat().st_size,
            }
        )
    )
    for archive_name in ["responses.jsonl.gz", "pdfs.tar.gz"]:
        print(
            archive_name, hashlib.sha256((ROOT / archive_name).read_bytes()).hexdigest()
        )


if __name__ == "__main__":
    main()
