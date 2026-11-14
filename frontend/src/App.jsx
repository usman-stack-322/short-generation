import Account from "./pages/Account";
import UploadHistory from "./pages/UploadHistory";
import Analytics from "./pages/Analytics";
import MediaLibrary from "./pages/MediaLibrary";
import CelebrityLibrary from "./pages/CelebrityLibrary";
import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { UploadProvider } from "./context/UploadContext";
import { Shell } from "./components/Shell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Personalities from "./pages/Personalities";
import TitleShort from "./pages/TitleShort";
import CreateShort from "./pages/CreateShort";
import Videos from "./pages/Videos";
import Review from "./pages/Review";
import Settings from "./pages/Settings";

export default function App() {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("user") || "null"); } catch { return null; }
  });
  function signIn(result) {
    localStorage.removeItem("workspace_id");
    localStorage.setItem("token", result.access_token);
    localStorage.setItem("user", JSON.stringify(result.user));
    localStorage.setItem("role", result.role || "OWNER");
    setUser(result.user);
  }
  const auth = (element) => localStorage.getItem("token") ? <Shell user={user}>{element}</Shell> : <Navigate to="/login" replace />;
  return <UploadProvider key={user?.id || "anon"}><Routes>
    <Route path="/login" element={localStorage.getItem("token") ? <Navigate to="/" replace /> : <Login onLogin={signIn} />} />
    <Route path="/register" element={<Login onLogin={signIn} initialMode="register" />} />
    <Route path="/join" element={<Navigate to="/register" replace />} />
    <Route path="/" element={auth(<Dashboard />)} />
    <Route path="/analytics" element={auth(<Analytics />)} />
    <Route path="/library" element={auth(<MediaLibrary />)} />
    <Route path="/celebrity-library" element={auth(<CelebrityLibrary />)} />
    <Route path="/review-queue" element={<Navigate to="/videos" replace />} />
    <Route path="/channels" element={<Navigate to="/" replace />} />
    <Route path="/team" element={<Navigate to="/" replace />} />
    <Route path="/personalities" element={auth(<Personalities />)} />
    <Route path="/create" element={auth(<CreateShort />)} />
    <Route path="/title-to-short" element={auth(<TitleShort />)} />
    <Route path="/title-to-short/:id" element={auth(<TitleShort />)} />
    <Route path="/title-short" element={<Navigate to="/title-to-short" replace />} />
    <Route path="/videos" element={auth(<Videos />)} />
    <Route path="/videos/:id" element={auth(<Review />)} />
    <Route path="/account" element={auth(<Account />)} />
    <Route path="/uploads" element={auth(<UploadHistory />)} />
    <Route path="/settings" element={auth(<Settings />)} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></UploadProvider>;
}
