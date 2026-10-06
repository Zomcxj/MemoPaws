import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { PinPage } from "./pages/PinPage";

const isPinWindow = window.location.hash === "#pin";
document.documentElement.dataset.window = isPinWindow ? "pin" : "main";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isPinWindow ? <PinPage /> : <App />}</React.StrictMode>
);
