import Account from "./pages/Account";
import UploadHistory from "./pages/UploadHistory";
import Analytics from "./pages/Analytics";
import MediaLibrary from "./pages/MediaLibrary";
import CelebrityLibrary from "./pages/CelebrityLibrary";
import ReviewQueue from "./pages/ReviewQueue";
import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Join from "./pages/Join";
import Team from "./pages/Team";
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
    localStorage.setItem("role", result.role);
    setUser(result.user);
  }
  const auth = (element) => localStorage.getItem("token") ? <Shell user={user}>{element}</Shell> : <Navigate to="/login" replace />;
  const adminOnly = (element) => auth(["OWNER", "ADMIN"].includes(localStorage.getItem("role")) ? element : <Navigate to="/" replace />);
  const creatorOnly = (element) => auth(localStorage.getItem("role") !== "VIEWER" ? element : <Navigate to="/" replace />);
  return <Routes>
    <Route path="/login" element={localStorage.getItem("token") ? <Navigate to="/" replace /> : <Login onLogin={signIn} />} />
    <Route path="/join" element={<Join onLogin={signIn} />} />
    <Route path="/" element={auth(<Dashboard />)} />
    <Route path="/analytics" element={adminOnly(<Analytics />)} />
    <Route path="/library" element={auth(<MediaLibrary />)} />
    <Route path="/celebrity-library" element={creatorOnly(<CelebrityLibrary />)} />
    <Route path="/review-queue" element={auth(<ReviewQueue />)} />
    <Route path="/channels" element={<Navigate to="/" replace />} />
    <Route path="/team" element={auth(<Team />)} />
    <Route path="/personalities" element={adminOnly(<Personalities />)} />
    <Route path="/create" element={adminOnly(<CreateShort />)} />
    <Route path="/title-to-short" element={creatorOnly(<TitleShort />)} />
    <Route path="/title-to-short/:id" element={creatorOnly(<TitleShort />)} />
    <Route path="/title-short" element={<Navigate to="/title-to-short" replace />} />
    <Route path="/videos" element={auth(<Videos />)} />
    <Route path="/videos/:id" element={adminOnly(<Review />)} />
    <Route path="/account" element={auth(<Account />)} />
    <Route path="/uploads" element={auth(<UploadHistory />)} />
    <Route path="/settings" element={adminOnly(<Settings />)} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
