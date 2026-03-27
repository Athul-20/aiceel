import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || "Unknown startup error" };
  }

  componentDidCatch(error, info) {
    console.error("Renderer startup error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "24px", fontFamily: "Inter, sans-serif", color: "#191919" }}>
          <h2 style={{ marginTop: 0 }}>AICCEL UI failed to start</h2>
          <p style={{ marginBottom: "8px" }}>The app hit a runtime error during startup.</p>
          <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{this.state.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <RootErrorBoundary>
    <App />
  </RootErrorBoundary>
);
