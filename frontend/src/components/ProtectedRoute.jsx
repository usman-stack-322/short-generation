import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, token, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#090B10] text-sm text-[#94A3B8]">
        <div className="flex items-center gap-3 rounded-xl border border-[#22283A] bg-[#131722] px-5 py-3">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[#F59E0B]" />
          Verifying studio session...
        </div>
      </div>
    );
  }

  if (!token || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}
