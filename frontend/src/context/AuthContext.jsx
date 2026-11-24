import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  clearAuthToken,
  getAuthToken,
  getCurrentUser,
  loginUser,
  registerUser,
  setAuthToken,
  setUnauthorizedHandler,
} from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => getAuthToken());
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(() => Boolean(getAuthToken()));

  const logout = useCallback(() => {
    clearAuthToken();
    setToken('');
    setUser(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    let cancelled = false;
    const storedToken = getAuthToken();
    if (!storedToken) {
      setLoading(false);
      return undefined;
    }

    setLoading(true);
    getCurrentUser()
      .then((profile) => {
        if (!cancelled) {
          setToken(storedToken);
          setUser(profile);
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearAuthToken();
          setToken('');
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async ({ email, password }) => {
    const result = await loginUser({ email, password });
    setAuthToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    setLoading(false);
    return result.user;
  }, []);

  const register = useCallback(async ({ email, password, displayName }) => {
    const result = await registerUser({ email, password, displayName });
    setAuthToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    setLoading(false);
    return result.user;
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return ctx;
}
