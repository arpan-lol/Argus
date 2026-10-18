export function fileIdentity(file: File) {
  return `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}`;
}

export function mergeFiles(current: File[], incoming: File[]) {
  const known = new Set(current.map(fileIdentity));
  const merged = [...current];
  for (const file of incoming) {
    const identity = fileIdentity(file);
    if (known.has(identity)) continue;
    known.add(identity);
    merged.push(file);
  }
  return merged;
}

export function formatBytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024).toFixed(0)} KB`;
}
