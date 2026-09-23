import { Routes, Route, Navigate } from "react-router-dom"
import { AuthProvider, useAuth } from "./context/AuthContext"
import LandingPage from "./pages/LandingPage"
import HomePage from "./pages/HomePage"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import NavigationFeature from "./pages/NavigationFeature"
import SearchFeature from "./pages/SearchFeature"
import ThreatFeature from "./pages/ThreatFeature"
import SceneFeature from "./pages/SceneFeature"
import VoiceFeature from "./pages/VoiceFeature"
import GestureTestFeature from "./pages/GestureTestFeature"
import AboutPage from "./pages/AboutPage"
import MissionPage from "./pages/MissionPage"
import ProfilePage from "./pages/ProfilePage"
import Contact from "./pages/Contact";
import AdminRoute from "./admin/AdminRoute"
import AdminLayout from "./admin/components/AdminLayout"
import AdminDashboard from "./admin/pages/AdminDashboard"
import AdminUsers from "./admin/pages/AdminUsers"
import AdminFlags from "./admin/pages/AdminFlags"
import AdminSettings from "./admin/pages/AdminSettings"
import AdminActivity from "./admin/pages/AdminActivity"

function ProtectedRoute({ children }) {
  const { token, checking } = useAuth()
  if (checking) return null
  if (!token) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/mission" element={<MissionPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/profile" element={
        <ProtectedRoute><ProfilePage /></ProtectedRoute>
      } />
      <Route path="/features/navigation" element={
        <ProtectedRoute><NavigationFeature /></ProtectedRoute>
      } />
      <Route path="/features/search" element={
        <ProtectedRoute><SearchFeature /></ProtectedRoute>
      } />
      <Route path="/features/threat" element={
        <ProtectedRoute><ThreatFeature /></ProtectedRoute>
      } />
      <Route path="/features/scene" element={
        <ProtectedRoute><SceneFeature /></ProtectedRoute>
      } />
      <Route path="/features/voice" element={
        <ProtectedRoute><VoiceFeature /></ProtectedRoute>
      } />
      <Route path="/gesture-test" element={<GestureTestFeature />} />
      <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
        <Route index element={<AdminDashboard />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="flags" element={<AdminFlags />} />
        <Route path="settings" element={<AdminSettings />} />
        <Route path="activity" element={<AdminActivity />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
