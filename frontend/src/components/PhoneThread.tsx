import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatDate, formatTime, minutesLeft } from "../format";
import type { ThreadData } from "../types";

/** The patient's text thread. Used by real phones at /p/<token> and inside the simulator. */
export function PhoneThread({ token }: { token: string }) {
  const [thread, setThread] = useState<ThreadData | null>(null);
  const [failed, setFailed] = useState(false);
  const [sending, setSending] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const count = thread?.messages.length ?? 0;

  const load = useCallback(async () => {
    try {
      setThread(await api.getThread(token));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [token]);

  useEffect(() => {
    let active = true;
    const tick = () => { if (active) load(); };
    tick();
    const timer = setInterval(tick, 1200);
    return () => { active = false; clearInterval(timer); };
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [count]);

  const send = async (text: string) => {
    setSending(true);
    setConfirmCancel(false);
    try {
      await api.reply(token, text);
      await load();
    } finally {
      setSending(false);
    }
  };

  if (!thread) {
    return (
      <div className="thread-page">
        <p className="empty">{failed ? "This link is no longer valid. Please call the clinic." : "Loading..."}</p>
      </div>
    );
  }

  return (
    <div className="thread-page">
      <div className="thread-head">
        <strong>Apollo</strong>
        <span>Text messages to {thread.patient.name}</span>
      </div>
      <div className="thread">
        {thread.messages.map((message) => (
          <div key={message.id} className={`bubble ${message.direction}`}>
            {message.body}
            <time>{formatTime(message.created_at)}</time>
          </div>
        ))}
        {thread.messages.length === 0 && <p className="muted">No messages yet.</p>}
        <div ref={bottom} />
      </div>
      {thread.can_answer_offer && (
        <div className="thread-actions">
          {thread.offer_expires_at && (
            <p className="hint">{minutesLeft(thread.offer_expires_at)} minutes left to reply</p>
          )}
          <div className="row">
            <button className="reply solid" disabled={sending} onClick={() => send("YES")}>Yes</button>
            <button className="reply" disabled={sending} onClick={() => send("NO")}>No</button>
          </div>
        </div>
      )}
      {!thread.can_answer_offer && thread.booking && (
        <div className="thread-actions">
          {confirmCancel ? (
            <>
              <p className="hint">Cancel {formatDate(thread.booking.date)} at {thread.booking.start}?</p>
              <div className="row">
                <button className="reply" disabled={sending} onClick={() => send("CANCEL")}>Yes, cancel it</button>
                <button className="reply quiet" onClick={() => setConfirmCancel(false)}>Keep it</button>
              </div>
            </>
          ) : (
            <div className="row">
              <button className="reply quiet" onClick={() => setConfirmCancel(true)}>Cancel appointment</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
