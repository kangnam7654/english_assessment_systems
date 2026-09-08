import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import ModelPreview from "./ModelPreview";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).get("preview") ===
    "assessment" ? (
      <ModelPreview />
    ) : (
      <App />
    )}
  </React.StrictMode>,
);
