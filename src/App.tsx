import { useEffect, useState } from "react";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import "./App.css";
import { Dashboard, Indicator } from "./components";

function App() {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    setLabel(getCurrentWebviewWindow().label);
  }, []);

  if (!label) return null;

  if (label === "main") {
    return (
      <div className="app-container">
        <Dashboard />
      </div>
    );
  }

  if (label === "indicator") {
    document.documentElement.classList.add("indicator-window");
    return (
      <div className="app-container app-container--indicator">
        <Indicator />
      </div>
    );
  }

  return null;
}

export default App;
