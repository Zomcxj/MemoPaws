import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { PinPage } from "./pages/PinPage";
import { CaptureOverlayPage } from "./pages/CaptureOverlayPage";

const isPinWindow = window.location.hash === "#pin";
const isOverlayWindow = window.location.hash === "#capture-overlay";
document.documentElement.dataset.window = isPinWindow ? "pin" : isOverlayWindow ? "capture" : "main";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isPinWindow ? <PinPage /> : isOverlayWindow ? <CaptureOverlayPage /> : <App />}</React.StrictMode>
);
