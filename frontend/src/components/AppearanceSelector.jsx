import { useEffect, useState } from 'react';

export default function AppearanceSelector() {
  const [value,setValue] = useState(() => window.aiShortsAppearance?.get() || 'system');
  useEffect(() => {
    const update = () => setValue(window.aiShortsAppearance?.get() || 'system');
    window.addEventListener('appearancechange',update);
    return () => window.removeEventListener('appearancechange',update);
  },[]);
  return <label className="appearance-selector"><span className="sr-only">Appearance</span><select aria-label="Appearance" value={value} onChange={event => window.aiShortsAppearance?.set(event.target.value)}><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label>;
}
