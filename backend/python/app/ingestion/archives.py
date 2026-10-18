import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .parsers import decode_source_text


EXCLUDED_DIRECTORIES = {'.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', '__pycache__', '.next', '.nuxt', '.turbo', '.cache', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'dist', 'build', 'coverage', '.idea', '.vscode'}
EXCLUDED_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tif', '.tiff', '.avif', '.heic', '.mp3', '.mp4', '.wav', '.ogg', '.webm', '.mov', '.avi', '.mkv', '.flac', '.woff', '.woff2', '.ttf', '.otf', '.eot', '.pyc', '.pyo', '.class', '.o', '.obj', '.so', '.dll', '.exe', '.bin', '.wasm', '.db', '.sqlite', '.sqlite3', '.pt', '.pth', '.safetensors', '.onnx', '.pem', '.key', '.p12', '.pfx', '.crt', '.cer', '.map', '.7z', '.rar', '.tar', '.tgz', '.bz2', '.xz'}
EXCLUDED_NAMES = {'.gitignore', '.gitattributes', '.gitmodules', '.npmrc', '.pypirc', '.netrc', '.ds_store', 'thumbs.db', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'poetry.lock', 'uv.lock', 'pipfile.lock', 'id_rsa', 'id_ed25519'}


def source_name(value):
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts) or not path.name:
        raise ValueError("Source paths must stay inside the uploaded folder")
    return str(path)


def skip_reason(filename):
    path = PurePosixPath(filename)
    name = path.name.lower()
    if any(part.lower() in EXCLUDED_DIRECTORIES for part in path.parts) or name == '.env' or name.startswith('.env.') and not name.endswith(('.example', '.sample', '.template')) or name in EXCLUDED_NAMES:
        return 'repository generated/private metadata'
    suffix = path.suffix.lower()
    if suffix == '.gz':
        suffix = PurePosixPath(path.stem).suffix.lower()
    if suffix in EXCLUDED_SUFFIXES:
        return 'image, media, generated output, private material or unsupported binary archive'
    return None


def content_skip_reason(path, filename):
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix in {'.pdf', '.docx', '.xlsx', '.pptx', '.eml', '.gz'}:
        return None
    try:
        with Path(path).open('rb') as source:
            raw = source.read(65536)
        decode_source_text(raw, partial=True)
    except (ValueError, OSError) as error:
        return str(error)
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
            reason = content_skip_reason(location, str(relative))
            if reason:
                skipped.append({"filename": str(relative), "reason": reason})
                continue
            extracted.append((location, str(relative)))
    return extracted, {"archive": filename, "extracted": len(extracted), "skipped": skipped}
