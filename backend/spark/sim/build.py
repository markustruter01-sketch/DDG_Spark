"""One command: generate an organisation's archive and prove its problems.

    uv run python -m spark.sim.build --org <name> --size small

Writes the archive to generated-artifacts/<org>/<size>/ and the answer key
next to it (outside the archive folder, so ingestion never sees it).
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from spark.sim.common import OUTPUT_ROOT, SIZES, ArchiveWriter, load_org
from spark.sim.export import export_world, incident_filename
from spark.sim.plant import plant_all
from spark.sim.recover import recover
from spark.sim.world import build_world


def build(org: str, size: str, output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    started = time.monotonic()
    config = load_org(org, size)
    world = build_world(config)
    answers = plant_all(world)
    for answer in answers:
        numbers = answer["finding"].get("incident_numbers")
        if numbers:
            answer["finding"]["files"] = [incident_filename(world, n) for n in numbers]
    root = output_root / org / size
    if root.exists():
        shutil.rmtree(root)
    writer = ArchiveWriter(root)
    export_world(world, writer)
    key_path = output_root / org / f"{size}-answer-key.yaml"
    key_path.write_text(
        yaml.safe_dump(
            {
                "organisation": config.org["name"],
                "size": size,
                "as_of": config.as_of.isoformat(),
                "problems": answers,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    results = recover(root, config.as_of, answers)
    total_bytes = sum((root / name).stat().st_size for name in writer.files)
    return {
        "organisation": config.org["name"],
        "size": size,
        "files": len(writer.files),
        "bytes": total_bytes,
        "checksum": writer.digest(),
        "seconds": round(time.monotonic() - started, 1),
        "archive": str(root),
        "answer_key": str(key_path),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True)
    parser.add_argument("--size", default="small", choices=SIZES)
    args = parser.parse_args()
    report = build(args.org, args.size)
    size_mb = report["bytes"] / 1e6
    print(
        f"{report['organisation']} ({report['size']}): {report['files']} files, "
        f"{size_mb:.1f} MB, {report['seconds']} s"
    )
    print(f"Checksum: {report['checksum']}")
    print(f"Archive: {report['archive']}")
    print(f"Answer key: {report['answer_key']}")
    failed = 0
    for r in report["results"]:
        status = "FOUND" if r["recovered"] else "NOT FOUND"
        failed += 0 if r["recovered"] else 1
        extras = len(r["extras"])
        print(f"  {status:9} {r['id']:24} flagged {r['flagged']}, extra {extras}")
    if failed:
        raise SystemExit(f"{failed} planted problem(s) not recovered.")


if __name__ == "__main__":
    main()
