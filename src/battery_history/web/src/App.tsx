/**
 * ZMK Battery History Module - Main Application
 *
 * Web UI for viewing battery consumption history from ZMK keyboards.
 * Features:
 * - Real-time battery level display
 * - Historical battery data visualization
 * - Statistics and estimated battery life
 */

import "./App.css";
import { connect as serial_connect } from "@zmkfirmware/zmk-studio-ts-client/transport/serial";
import { ZMKConnection } from "@cormoran/zmk-studio-react-hook";

import {
  BatteryHistorySection,
  BATTERY_HISTORY_SUBSYSTEM,
} from "./components/BatteryHistorySection";

// Custom subsystem identifier for battery history - must match firmware registration
export const SUBSYSTEM_IDENTIFIER = BATTERY_HISTORY_SUBSYSTEM;

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>🔋 Battery History</h1>
        <p>Monitor your keyboard's battery consumption over time</p>
      </header>

      <ZMKConnection
        renderDisconnected={({ connect, isLoading, error }) => (
          <section className="card connect-card">
            <div className="connect-content">
              <div className="connect-icon">⌨️</div>
              <h2>Connect Your Keyboard</h2>
              <p>Connect via USB serial to view battery history data.</p>

              {isLoading && (
                <div className="loading-indicator">
                  <span className="loading-spinner"></span>
                  <span>Connecting...</span>
                </div>
              )}

              {error && (
                <div className="error-message">
                  <p>🚨 {error}</p>
                </div>
              )}

              {!isLoading && (
                <button
                  className="btn btn-primary btn-large"
                  onClick={() => connect(serial_connect)}
                >
                  🔌 Connect via USB
                </button>
              )}

              <p className="connect-hint">
                Make sure your keyboard is connected and has Studio mode
                enabled.
              </p>
            </div>
          </section>
        )}
        renderConnected={({ disconnect, deviceName }) => (
          <>
            <section className="card device-card">
              <div className="device-status">
                <div className="device-info">
                  <span className="status-indicator connected"></span>
                  <span className="device-name">{deviceName}</span>
                </div>
                <button
                  className="btn btn-secondary btn-small"
                  onClick={disconnect}
                >
                  Disconnect
                </button>
              </div>
            </section>

            <BatteryHistorySection />
          </>
        )}
      />

      <footer className="app-footer">
        <p>
          <strong>ZMK Battery History Module</strong>
        </p>
        <p className="footer-hint">
          Data is stored on your keyboard and fetched each time you connect.
        </p>
      </footer>
    </div>
  );
}

export default App;
