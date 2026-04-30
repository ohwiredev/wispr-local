import { useEffect, useState } from "react";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import "./App.css";
import { Dashboard, Indicator, TitleBar } from "./components";

function App() {
  const [label, setLabel] = useState<string | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    const window = getCurrentWebviewWindow();
    setLabel(window.label);

    if (window.label === "main") {
      const updateMaximized = async () => {
        setIsMaximized(await window.isMaximized());
      };
      updateMaximized();
      const unlisten = window.onResized(() => updateMaximized());
      return () => { unlisten.then(f => f()); };
    }
  }, []);

  if (!label) return null;

  if (label === "main") {
    return (
      <div className={`app-container app-container--main ${isMaximized ? "is-maximized" : ""}`}>
        <TitleBar />
        <div className="main-layout">
          <Dashboard />
        </div>
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
