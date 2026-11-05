import { useLanguages } from '../hooks/useLanguages';

export default function LanguageSelect({ value, onChange, disabled = false, label = 'Language' }) {
  const { languages, error } = useLanguages();
  const canonical = languages.find(item => item.code === value || item.code.split('-')[0] === value)?.code || value;
  return <label>{label}<select value={canonical} disabled={disabled || !languages.length} onChange={e => onChange(e.target.value)}>
    {!languages.length && <option value={value}>{error ? 'Languages unavailable' : 'Loading languages…'}</option>}
    {languages.map(item => <option key={item.code} value={item.code}>{item.name} ({item.locale})</option>)}
  </select>{error && <small role="alert">{error}</small>}</label>;
}
