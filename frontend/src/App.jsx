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
import Team from "./pages/Team";
import Channels from "./pages/Channels";
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
    localStorage.setItem("token", result.access_token);
    localStorage.setItem("user", JSON.stringify(result.user));
    localStorage.setItem("role", result.role);
    setUser(result.user);
  }
  const auth = (element) => localStorage.getItem("token") ? <Shell user={user}>{element}</Shell> : <Navigate to="/login" replace />;
  return <Routes>
    <Route path="/login" element={localStorage.getItem("token") ? <Navigate to="/" replace /> : <Login onLogin={signIn} />} />
    <Route path="/" element={auth(<Dashboard />)} />
    <Route path="/analytics" element={auth(<Analytics />)} />
    <Route path="/library" element={auth(<MediaLibrary />)} />
    <Route path="/celebrity-library" element={auth(<CelebrityLibrary />)} />
    <Route path="/review-queue" element={auth(<ReviewQueue />)} />
    <Route path="/channels" element={auth(<Channels />)} />
    <Route path="/team" element={auth(["OWNER","ADMIN"].includes(localStorage.getItem("role")) ? <Team /> : <Navigate to="/" replace />)} />
    <Route path="/personalities" element={auth(<Personalities />)} />
    <Route path="/create" element={auth(localStorage.getItem("role") !== "VIEWER" ? <CreateShort /> : <Navigate to="/" replace />)} />
    <Route path="/title-to-short" element={auth(localStorage.getItem("role") !== "VIEWER" ? <TitleShort /> : <Navigate to="/" replace />)} />
    <Route path="/title-to-short/:id" element={auth(localStorage.getItem("role") !== "VIEWER" ? <TitleShort /> : <Navigate to="/" replace />)} />
    <Route path="/videos" element={auth(<Videos />)} />
    <Route path="/videos/:id" element={auth(<Review />)} />
    <Route path="/account" element={auth(<Account />)} />
    <Route path="/uploads" element={auth(<UploadHistory />)} />
    <Route path="/settings" element={auth(["OWNER","ADMIN"].includes(localStorage.getItem("role")) ? <Settings /> : <Navigate to="/account" replace />)} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
