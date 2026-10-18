const pending = new Map<string, File[]>();

export function stageProjectUpload(projectId: string, files: File[]) {
  if (files.length) pending.set(projectId, files);
}

export function takeProjectUpload(projectId: string) {
  const files = pending.get(projectId);
  pending.delete(projectId);
  return files;
}
