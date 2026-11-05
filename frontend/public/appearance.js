// Synchronous, before CSS/React: avoids a light flash and works without storage.
(() => {
  const key = 'ai-shorts-appearance';
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';
  try { preference = localStorage.getItem(key) || 'system'; } catch {}
  if (!['light', 'dark', 'system'].includes(preference)) preference = 'system';
  function apply() {
    const theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.appearance = preference;
    document.documentElement.style.colorScheme = theme;
    window.dispatchEvent(new Event('appearancechange'));
  }
  window.aiShortsAppearance = {
    get: () => preference,
    set(value) { if (!['light','dark','system'].includes(value)) return; preference = value; try { localStorage.setItem(key,value); } catch {} apply(); }
  };
  media.addEventListener('change', apply);
  window.addEventListener('storage', event => { if(event.key === key) { preference = ['light','dark','system'].includes(event.newValue) ? event.newValue : 'system'; apply(); } });
  apply();
})();
