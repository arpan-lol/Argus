'use client';

import { useEffect, useId, useState } from 'react';
import { api } from '@/lib/evidence-types';
import './CategorySelection.css';

interface Category { id: string; name: string; description: string }

export function CategorySelection({ value, onChange, disabled = false }: { value: string[]; onChange: (values: string[]) => void; disabled?: boolean }) {
  const id = useId();
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    api<{ categories: Category[] }>('/projects/categories').then(result => { if (active) setCategories(result.categories); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load categories'); });
    return () => { active = false; };
  }, [version]);
  return <fieldset className="argus-categories" disabled={disabled} aria-describedby={`${id}-help`}>
    <legend>Document categories</legend>
    <p id={`${id}-help`}>Choose all that apply · Sets the initial entity and relationship types for this workspace</p>
    {error ? <div className="argus-categories-error" role="alert">{error}<button type="button" onClick={() => setVersion(current => current + 1)}>Try again</button></div> : !categories.length ? <p role="status">Loading categories…</p> : <div className="argus-category-options">{categories.map(category => <label key={category.id} title={category.description}><input type="checkbox" checked={value.includes(category.id)} onChange={event => onChange(event.target.checked ? [...value, category.id] : value.filter(item => item !== category.id))} /><span>{category.name}</span></label>)}</div>}
  </fieldset>;
}
