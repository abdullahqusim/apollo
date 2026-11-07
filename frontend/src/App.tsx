import { PhoneSimulator } from "./components/PhoneSimulator";
import { PhoneThread } from "./components/PhoneThread";
import { ConsolePage } from "./pages/ConsolePage";
import { JoinPage } from "./pages/JoinPage";

export default function App() {
  const path = window.location.pathname;
  if (path.startsWith("/join")) return <JoinPage />;
  if (path.startsWith("/p/")) return <PhoneThread token={path.split("/")[2]} />;
  if (path.startsWith("/phone")) {
    return (
      <div className="phone-dock" style={{ width: 380, height: "100%", margin: "0 auto" }}>
        <PhoneSimulator token={null} onPick={() => undefined} />
      </div>
    );
  }
  return <ConsolePage />;
}
