import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .code_parser import CODE_SUFFIXES
from .parser_routing import TEXT_SUFFIXES
from .parsers import SUPPORTED


def source_name(value):
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts) or not path.name:
        raise ValueError("Source paths must stay inside the uploaded folder")
    return str(path)


def skip_reason(filename):
    path = PurePosixPath(filename)
    if any(part in {'.git', 'node_modules', '.venv', '__pycache__'} for part in path.parts) or path.name == '.env':
        return 'repository generated/private metadata'
    suffix = path.suffix.lower()
    if suffix == '.gz':
        suffix = PurePosixPath(path.stem).suffix.lower()
    if suffix not in SUPPORTED | TEXT_SUFFIXES | CODE_SUFFIXES and path.name not in {'LICENSE', 'NOTICE', 'Dockerfile', '.gitignore'}:
        return 'unsupported file format'
    return None


def expand_archive(path, filename, config, temporary):
    extracted = []
    skipped = []
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > config["maxArchiveMembers"] or sum(item.file_size for item in entries) > config["maxDecompressedBytes"]:
            raise ValueError("Archive exceeds configured entry or expanded-byte limit")
        files = [item for item in entries if not item.is_dir()]
        names = [PurePosixPath(source_name(item.filename)) for item in files]
        roots = {name.parts[0] for name in names}
        strip_root = len(roots) == 1 and all(len(name.parts) > 1 for name in names)
        for entry, name in zip(files, names, strict=True):
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError("Encrypted entries and symbolic links cannot be ingested")
            relative = PurePosixPath(*name.parts[1:]) if strip_root else name
            reason = skip_reason(str(relative))
            if reason:
                skipped.append({"filename": str(relative), "reason": reason})
                continue
            if not entry.file_size:
                skipped.append({"filename": str(relative), "reason": "empty file"})
                continue
            if entry.file_size > config["maxUploadBytes"]:
                raise ValueError("An archive source exceeds the configured per-file limit")
            raw = archive.read(entry)
            if len(raw) != entry.file_size:
                raise ValueError("Archive entry size did not match its manifest")
            with tempfile.NamedTemporaryFile(delete=False, suffix="-" + relative.name) as target:
                target.write(raw)
                location = Path(target.name)
            temporary.append(location)
            extracted.append((location, str(relative)))
    return extracted, {"archive": filename, "extracted": len(extracted), "skipped": skipped}
