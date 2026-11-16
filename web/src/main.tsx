import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { installTokenProvider } from "./lib/auth";
import "./styles/tokens.css";

if (import.meta.env.VITE_DEMO === "1") {
  // The demo never signs in and never calls an API: it serves a recorded snapshot (D-79).
  const { installDemo } = await import("./demo/install");
  installDemo();
} else {
  installTokenProvider();
}

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
