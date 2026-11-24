import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Clapperboard, Eye, EyeOff, Lock, Mail, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { user, token, login, register } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [mode, setMode] = useState('login');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const fromPath = location.state?.from?.pathname || '/';

  if (token && user) {
    return <Navigate to={fromPath} replace />;
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    const cleanEmail = email.trim();
    if (!cleanEmail) {
      setError('Please enter your email address.');
      return;
    }
    if (mode === 'signup' && password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'signup') {
        await register({
          email: cleanEmail,
          password,
          displayName: displayName.trim(),
        });
      } else {
        await login({ email: cleanEmail, password });
      }
      navigate(fromPath, { replace: true });
    } catch (err) {
      setError(err.message || 'Authentication failed.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#090B10] px-4 py-12 text-[#F8FAFC]">
      <div className="w-full max-w-md space-y-6">
        <div className="flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#F59E0B] text-[#090B10] shadow-lg shadow-[#F59E0B]/15">
            <Clapperboard className="h-6 w-6" />
          </div>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-[#F8FAFC]">
            AI Shorts Studio
          </h1>
          <p className="mt-1 text-sm text-[#94A3B8]">
            {mode === 'login'
              ? 'Sign in to access your Celebrity Vault and render queue.'
              : 'Create a creator account to start building NBA & celebrity Shorts.'}
          </p>
        </div>

        <div className="rounded-xl border border-[#22283A] bg-[#131722] p-6">
          <div className="mb-6 grid grid-cols-2 rounded-lg border border-[#22283A] bg-[#090B10] p-1">
            <button
              type="button"
              onClick={() => switchMode('login')}
              className={`rounded-md py-2 text-sm font-medium transition ${
                mode === 'login'
                  ? 'bg-[#131722] text-[#F59E0B] ring-1 ring-[#F59E0B]/40'
                  : 'text-[#94A3B8] hover:text-[#F8FAFC]'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => switchMode('signup')}
              className={`rounded-md py-2 text-sm font-medium transition ${
                mode === 'signup'
                  ? 'bg-[#131722] text-[#F59E0B] ring-1 ring-[#F59E0B]/40'
                  : 'text-[#94A3B8] hover:text-[#F8FAFC]'
              }`}
            >
              Sign Up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'signup' && (
              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Creator Name (Optional)
                </label>
                <div className="relative mt-1.5">
                  <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="e.g. Courtside Edits"
                    className="w-full rounded-lg border border-[#22283A] bg-[#090B10] py-2.5 pl-9 pr-3 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/50 focus:border-[#F59E0B] focus:outline-none"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-[#94A3B8]">
                Email Address
              </label>
              <div className="relative mt-1.5">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@studio.com"
                  className="w-full rounded-lg border border-[#22283A] bg-[#090B10] py-2.5 pl-9 pr-3 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/50 focus:border-[#F59E0B] focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-[#94A3B8]">
                Password
              </label>
              <div className="relative mt-1.5">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={mode === 'signup' ? 6 : 1}
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === 'signup' ? 'At least 6 characters' : 'Enter your password'}
                  className="w-full rounded-lg border border-[#22283A] bg-[#090B10] py-2.5 pl-9 pr-10 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/50 focus:border-[#F59E0B] focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-[#94A3B8] hover:text-[#F8FAFC]"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-3.5 py-2.5 text-xs text-[#F43F5E]">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-[#F59E0B] py-2.5 text-sm font-semibold text-[#090B10] transition hover:bg-[#D97706] disabled:opacity-60"
            >
              {submitting
                ? mode === 'signup'
                  ? 'Creating account...'
                  : 'Signing in...'
                : mode === 'signup'
                ? 'Create Account'
                : 'Sign In'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
