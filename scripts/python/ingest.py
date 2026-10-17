import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "python"))

from app.ingestion import IngestionPipeline, initialize
from app.ingestion.pipeline import STAGES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--glob", dest="pattern")
    parser.add_argument("--through", choices=STAGES, default="publish")
    parser.add_argument("--resume")
    parser.add_argument("--register-only", action="store_true")
    parser.add_argument("--source-id")
    parser.add_argument("--source-url")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    initialize()
    pipeline = IngestionPipeline()
    if args.resume:
        result = pipeline.run_job(args.resume, args.through)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    paths = [Path(value) for value in args.paths]
    if args.pattern:
        import glob
        paths.extend(Path(value) for value in sorted(glob.glob(args.pattern)))
    if args.limit is not None:
        paths = paths[:args.limit]
    if not paths:
        parser.error("Provide paths, --glob, or --resume")
    for path in paths:
        source_id = args.source_id
        stem = path.name.removesuffix(".gz").removesuffix(".xml")
        if source_id is None and stem.startswith("PMC") and stem[3:].isdigit():
            source_id = stem
        result = pipeline.register_file(path, source_id=source_id, source_url=args.source_url)
        if not args.register_only:
            result = pipeline.run_job(result["id"], args.through)
        print(json.dumps({key: result[key] for key in ("id", "documentId", "filename", "status", "currentStage", "chunkCount", "error")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
