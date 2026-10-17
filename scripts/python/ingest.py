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
    parser.add_argument("--prompt")
    parser.add_argument("--profile-id")
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
    if args.source_id and len(paths) != 1:
        parser.error("--source-id applies to one file; omit it for a corpus import")
    if args.prompt and args.profile_id:
        parser.error("Supply --prompt or --profile-id, not both")
    def identifier(path):
        stem = path.name.removesuffix(".gz").removesuffix(".xml")
        return args.source_id or (stem if stem.startswith("PMC") and stem[3:].isdigit() else None)
    profile_id = args.profile_id
    if args.prompt:
        from app.ingestion.profiles import create_profile
        sources = [pipeline.describe_source(path, source_id=identifier(path), source_url=args.source_url) for path in paths]
        profile_id = create_profile(args.prompt, sources)["id"]
        print(json.dumps({"profileId": profile_id, "status": "pending", "automatic": True}), flush=True)
    for path in paths:
        result = pipeline.register_file(path, source_id=identifier(path), source_url=args.source_url, profile_id=profile_id)
        if not args.register_only:
            result = pipeline.run_job(result["id"], args.through)
        print(json.dumps({key: result[key] for key in ("id", "documentId", "filename", "status", "currentStage", "chunkCount", "error")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
