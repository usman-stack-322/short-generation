import { useEffect, useState } from 'react';
import { api } from '../services/api';

let catalog;
export function useLanguages() {
  const [languages, setLanguages] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    catalog ??= api('/languages').catch(error => { catalog = null; throw error; });
    catalog.then(rows => { if (live) setLanguages(rows); }).catch(err => { if (live) setError(err.message); });
    return () => { live = false; };
  }, []);
  return { languages, error };
}
