import { useEffect, type ReactNode } from "react";

export function Dialog({ title, width = 480, onClose, children, footer }: {
  title: string;
  width?: number;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="overlay">
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title} style={{ maxWidth: width }}>
        <div className="winbar">
          <span>{title}</span>
          <button className="close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="body">{children}</div>
        <div className="footer">{footer}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({ title, message, confirmLabel, cancelLabel = "Cancel", busy, error, onConfirm, onClose }: {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      title={title}
      width={400}
      onClose={onClose}
      footer={
        <>
          <button className="btn primary" disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
          <button className="btn" onClick={onClose}>{cancelLabel}</button>
        </>
      }
    >
      <p className="message">{message}</p>
      {error && <p className="form-error">{error}</p>}
    </Dialog>
  );
}
