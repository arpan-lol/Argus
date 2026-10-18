import { SourceWorkspace } from '@/components/workspace/SourceWorkspace';
import { redirect } from 'next/navigation';

export default async function Dashboard({ searchParams }: { searchParams: Promise<{ project?: string }> }) {
  const { project } = await searchParams;
  if (!project || !/^[a-f0-9-]{36}$/i.test(project)) redirect('/');
  return <SourceWorkspace key={project} projectId={project} />;
}
