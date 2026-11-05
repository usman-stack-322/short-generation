export const voiceStyles = ['auto', 'professional', 'news', 'documentary', 'energetic', 'funny', 'emotional', 'motivational', 'educational', 'dramatic', 'luxury', 'conversational', 'sports_hype', 'serious'];
export const styleLabel = value => value === 'auto' ? 'Auto — Recommended' : (value || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());

export default function VoiceStyleSelect({ value = 'auto', onChange, disabled = false }) {
  return <label>Voice Style<select value={value} onChange={e => onChange(e.target.value)} disabled={disabled}>
    {voiceStyles.map(style => <option key={style} value={style}>{styleLabel(style)}</option>)}
  </select></label>;
}
