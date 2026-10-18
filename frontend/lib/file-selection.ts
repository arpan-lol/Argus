const fileIds = new WeakMap<File, number>();
let nextFileId = 0;

export function fileIdentity(file: File) {
  let id = fileIds.get(file);
  if (id === undefined) {
    id = ++nextFileId;
    fileIds.set(file, id);
  }
  return `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}:${id}`;
}

export function mergeFiles(current: File[], incoming: File[]) {
  const known = new Set(current);
  const merged = [...current];
  for (const file of incoming) {
    if (known.has(file)) continue;
    known.add(file);
    merged.push(file);
  }
  return merged;
}

export function formatBytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024).toFixed(0)} KB`;
}
