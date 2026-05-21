import ChatWindow from "./components/ChatWindow";

export default function Home() {
  return (
    <div className="App">
      <header className="app-header">
        <div className="header-inner">
          <div className="logo-group">
            <span className="logo-ps">Part</span>
            <span className="logo-select">Select</span>
            <span className="header-divider" />
            <span className="header-subtitle">Parts Assistant</span>
          </div>
          <span className="header-badge">Refrigerators &amp; Dishwashers</span>
        </div>
      </header>
      <ChatWindow />
    </div>
  );
}
