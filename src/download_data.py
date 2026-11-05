"""Download the SCANIA Component X dataset (v3) from the Swedish National Data Service.

Usage:
    python src/download_data.py               # download all 9 files into data/raw/
    python src/download_data.py --skip-verify # don't check SHA-256 (not recommended)

Files that already exist with the right checksum are skipped, so it is safe to rerun.
No account or API key is needed. Total size is about 1.65 GB.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://api.researchdata.se/dataset/2024-34/3/file/data/"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# SHA-256 checksums as published for version 3 (DOI 10.5878/bnh5-ka77).
FILES = {
    "train_operational_readouts.csv": "e01cb0bd87dfab4c9dbad215d51d81282fc0d413be96d6f819ea872fb7a3c715",
    "train_specifications.csv": "47cc9a67aee19d5e2ee8620fe8e467490b2125bacc7787ce781ce9f3c1f0c38f",
    "train_tte.csv": "d8c2379ed7c95a575dd869730b2b3b96d660317f49e57de300518ff3b08d53a5",
    "validation_operational_readouts.csv": "1e1597eec866588c2ad95eb923555ad719c64b3697d9140f9cec6809349809af",
    "validation_specifications.csv": "a31e832846538dd7a1829108b69420d9377dcd05d6446d8ac1270a974fc58ae2",
    "validation_labels.csv": "ad876c95c3696f4cfca2d76212ad6bb3cac6b2d2950a4aeaf218ee8b1548d08c",
    "test_operational_readouts.csv": "81f2709cd339e0ff561f5fd3188d7f431680e32400bd788814880d7759615ba1",
    "test_specifications.csv": "40ac8a111f6d5b416107ec1786f639766ecf1293a1c9c0c0dbf24f14c1c5d0e7",
    "test_labels.csv": "60f923051d4ba1bef4c81166cf9e8ca01daf3b7a29c73016c6f48a23dcfa0223",
}
CHUNK = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(name: str, url: str, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "truck-pdm-portfolio/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        for block in iter(lambda: response.read(CHUNK), b""):
            out.write(block)
            done += len(block)
            if total:
                print(f"\r  {name}: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="", flush=True)
            else:
                print(f"\r  {name}: {done / 1e6:,.0f} MB", end="", flush=True)
    print()
    partial.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-verify", action="store_true", help="skip SHA-256 checks")
    parser.add_argument("--base-url", default=BASE_URL, help=argparse.SUPPRESS)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, expected in FILES.items():
        target = RAW_DIR / name
        if target.exists() and (args.skip_verify or sha256(target) == expected):
            print(f"  {name}: already present, skipping")
            continue
        try:
            download(name, args.base_url + name, target)
        except Exception as error:  # network errors, HTTP errors
            print(f"\n  {name}: download failed: {error}")
            failures.append(name)
            continue
        if not args.skip_verify:
            actual = sha256(target)
            if actual != expected:
                print(f"  {name}: CHECKSUM MISMATCH (got {actual[:12]}..., expected {expected[:12]}...)")
                failures.append(name)

    if failures:
        print(f"\n{len(failures)} file(s) failed: {', '.join(failures)}")
        print("Rerun the script; if a checksum keeps failing, check the dataset page "
              "https://doi.org/10.5878/bnh5-ka77 for a newer version.")
        return 1
    print(f"\nAll {len(FILES)} files in {RAW_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
