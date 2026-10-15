import { Navigate, Route, Routes } from "react-router-dom";
import DirectoryPage from "./pages/DirectoryPage";
import ProfilePage from "./pages/ProfilePage";
import AskPage from "./pages/AskPage";
import ReviewsPage from "./pages/ReviewsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/students" replace />} />
      <Route path="/students" element={<DirectoryPage />} />
      <Route path="/students/:learnerId/ask" element={<AskPage />} />
      <Route path="/students/:learnerId" element={<ProfilePage />} />
      <Route path="/reviews" element={<ReviewsPage />} />
      <Route path="/reviews/:reviewId" element={<ReviewsPage />} />
      <Route path="*" element={<Navigate to="/students" replace />} />
    </Routes>
  );
}
