import qrcode from "qrcode-generator";
import { useMemo } from "react";
import { Dialog } from "./Dialog";

export function SignupDialog({ onClose }: { onClose: () => void }) {
  const url = `${window.location.origin}/join`;
  const image = useMemo(() => {
    const code = qrcode(0, "M");
    code.addData(url);
    code.make();
    return code.createDataURL(6, 8);
  }, [url]);

  return (
    <Dialog title="Online sign-up" width={440} onClose={onClose} footer={<button className="btn" onClick={onClose}>Close</button>}>
      <div className="qr-row">
        <img src={image} alt={`QR code for ${url}`} />
        <div>
          <p>Scan to register online. It asks the same questions as the phone line.</p>
          <p className="muted small">{url}</p>
        </div>
      </div>
    </Dialog>
  );
}
