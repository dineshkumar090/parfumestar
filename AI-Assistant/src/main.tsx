import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Expose Vite env variables globally for external scripts
window.__ENV__ = {
  VITE_PYTHON_API_URL: import.meta.env.VITE_PYTHON_API_URL
};

createRoot(document.getElementById("root")!).render(<App />);