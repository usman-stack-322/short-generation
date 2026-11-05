import logo from '../assets/ai-shorts-logo.png';

export default function BrandLogo({ compact = false }) {
  return <picture className="ai-shorts-brand">
    {compact && <source media="(min-width: 601px) and (max-width: 820px)" srcSet="/favicon.png" />}
    <img src={logo} alt="AI Shorts" className="ai-shorts-logo" />
  </picture>;
}
