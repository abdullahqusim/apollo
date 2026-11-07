import { useCallback, useEffect, useRef, useState } from "react";
import { api, type IntakeResult } from "../api";
import { AssignDialog } from "../components/AssignDialog";
import { AuditLogView } from "../components/AuditLogView";
import { CallDialog } from "../components/CallDialog";
import { CliniciansView } from "../components/CliniciansView";
import { ConfirmDialog } from "../components/Dialog";
import { PatientRecord } from "../components/PatientRecord";
import { PhoneSimulator } from "../components/PhoneSimulator";
import { ReplayDialog } from "../components/ReplayDialog";
import { ScheduleView } from "../components/ScheduleView";
import { SignupDialog } from "../components/SignupDialog";
import { WaitingListView } from "../components/WaitingListView";
import { WorklistView } from "../components/WorklistView";
import { OUTCOME_TEXT } from "../format";
import type {
  AuditEvent, Call, ClinicianData, ReleasedSlot, Role, SlotItem, TodayData, WaitingCase, WorklistItem,
} from "../types";

type View = "schedule" | "worklist" | "waiting" | "clinicians" | "audit";
type Modal = "call" | "signup" | "replay" | "reset" | null;

interface ConsoleData {
  day: TodayData;
  released: ReleasedSlot[];
  worklist: WorklistItem[];
  calls: Call[];
  waiting: WaitingCase[];
  clinicians: ClinicianData;
  audit: AuditEvent[];
}

const POLL_MS = 1500;
const DOCK_WIDTH = 340;

export function ConsolePage() {
  const [view, setView] = useState<View>("schedule");
  const [role, setRole] = useState<Role>("receptionist");
  const [data, setData] = useState<ConsoleData | null>(null);
  const [offline, setOffline] = useState(false);
  const dateRef = useRef<string | null>(null);

  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [patientId, setPatientId] = useState<string | null>(null);
  const [assignCase, setAssignCase] = useState<string | null>(null);
  const [cancelSlot, setCancelSlot] = useState<SlotItem | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [phoneOpen, setPhoneOpen] = useState(true);
  const [phoneToken, setPhoneToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [day, released, worklist, calls, waiting, clinicians, audit] = await Promise.all([
        api.getDay(dateRef.current), api.getReleased(), api.getWorklist(), api.getCalls(),
        api.getWaitingList(), api.getClinicians(), api.getAuditLog(),
      ]);
      setData({
        day,
        released: released.released,
        worklist: worklist.items,
        calls: calls.calls,
        waiting: waiting.cases,
        clinicians,
        audit: audit.events,
      });
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const tick = () => { if (active) refresh(); };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => { active = false; clearInterval(timer); };
  }, [refresh]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 8000);
    return () => clearTimeout(timer);
  }, [notice]);

  const closeModal = useCallback(() => { setModal(null); setActionError(null); }, []);
  const closeCancel = useCallback(() => { setCancelSlot(null); setActionError(null); }, []);
  const closeAssign = useCallback(() => setAssignCase(null), []);
  const closeRecord = useCallback(() => setPatientId(null), []);
  const openPhone = useCallback((token: string) => { setPhoneToken(token); setPhoneOpen(true); }, []);

  const selectChair = (slotId: string) => {
    setSelectedSlot(slotId);
    const token = data?.day.slots.find((s) => s.slot_id === slotId)?.patient?.token;
    if (token) setPhoneToken(token);
  };

  const goToDate = (next: string, slotId?: string) => {
    dateRef.current = next;
    setSelectedSlot(slotId ?? null);
    setView("schedule");
    refresh();
  };

  const run = async (action: () => Promise<unknown>, after: () => void) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await refresh();
      after();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const callFinished = (result: IntakeResult) => {
    setNotice(OUTCOME_TEXT[result.outcome] ?? "Call processed.");
    if (result.token) openPhone(result.token);
    refresh();
  };

  const chooseTool = (action: () => void) => { setMenuOpen(false); action(); };
  const openItems = data?.worklist.filter((item) => item.status === "open").length ?? 0;
  const tabs: { id: View; label: string; count?: number }[] = [
    { id: "schedule", label: "Schedule" },
    { id: "worklist", label: "Worklist", count: openItems },
    { id: "waiting", label: "Waiting list" },
    { id: "clinicians", label: "Clinicians" },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">Apollo</h1>
        <nav className="tabs" role="tablist">
          {tabs.map((tab) => (
            <button key={tab.id} className="tab" role="tab" aria-selected={view === tab.id} onClick={() => setView(tab.id)}>
              {tab.label}
              {!!tab.count && <span className="count">{tab.count}</span>}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <label>
          View as
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="receptionist">Reception</option>
            <option value="clinical">Clinical</option>
          </select>
        </label>
        <button className="nav-btn" aria-pressed={phoneOpen} onClick={() => setPhoneOpen(!phoneOpen)}>Patient phone</button>
        <div className="menu" ref={menuRef}>
          <button className="nav-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>Tools ▾</button>
          {menuOpen && (
            <div className="menu-list" role="menu">
              <button role="menuitem" onClick={() => chooseTool(() => setModal("call"))}>Simulate a call</button>
              <button role="menuitem" onClick={() => chooseTool(() => setModal("signup"))}>Online sign-up QR code</button>
              <hr />
              <button role="menuitem" onClick={() => chooseTool(() => setView("audit"))}>Audit log</button>
              <button role="menuitem" onClick={() => chooseTool(() => setModal("replay"))}>Replay a week</button>
              <button role="menuitem" onClick={() => chooseTool(() => setModal("reset"))}>Reset demo data</button>
            </div>
          )}
        </div>
      </header>

      <div className="workspace">
        <main className={`content ${view === "schedule" ? "fit" : ""}`}>
          {notice && (
            <p className="notice" role="status">
              {notice} <button className="link" onClick={() => setNotice(null)}>Dismiss</button>
            </p>
          )}
          {!data && <p className="empty">{offline ? "Cannot reach the server." : "Loading..."}</p>}
          {data && view === "schedule" && (
            <ScheduleView
              day={data.day}
              released={data.released}
              selectedId={selectedSlot}
              onSelect={selectChair}
              onChangeDate={goToDate}
              onOpenPatient={setPatientId}
              onOpenPhone={openPhone}
              onCancel={setCancelSlot}
              onFindPatient={() => setView("waiting")}
              onChanged={refresh}
              onClearSelection={() => setSelectedSlot(null)}
            />
          )}
          {data && view === "worklist" && (
            <WorklistView
              items={data.worklist}
              calls={data.calls}
              onOpenPatient={setPatientId}
              onOpenSlot={goToDate}
              onClose={(id, action) => run(
                () => api.closeWorklistItem(id, action, action === "resolve" ? "Approved" : "Dismissed"),
                () => undefined,
              )}
            />
          )}
          {data && view === "waiting" && (
            <WaitingListView cases={data.waiting} role={role} onOpenPatient={setPatientId} onAssign={setAssignCase} onChanged={refresh} />
          )}
          {data && view === "clinicians" && <CliniciansView data={data.clinicians} />}
          {data && view === "audit" && <AuditLogView events={data.audit} />}
        </main>
        {phoneOpen && (
          <aside className="phone-dock" aria-label="Patient phone">
            <PhoneSimulator token={phoneToken} onPick={setPhoneToken} />
          </aside>
        )}
      </div>

      <footer className="statusline">
        {offline ? <span className="bad">Connection lost, retrying</span> : <span>Connected</span>}
        <span>Demo data</span>
      </footer>

      {patientId && (
        <PatientRecord
          patientId={patientId}
          role={role}
          panelRight={phoneOpen && window.innerWidth > 900 ? DOCK_WIDTH : 0}
          onClose={closeRecord}
          onChanged={refresh}
          onOpenPhone={openPhone}
          onLoaded={setPhoneToken}
        />
      )}
      {assignCase && <AssignDialog caseId={assignCase} onClose={closeAssign} onAssigned={refresh} />}
      {modal === "call" && <CallDialog onClose={closeModal} onDone={callFinished} />}
      {modal === "signup" && <SignupDialog onClose={closeModal} />}
      {modal === "replay" && <ReplayDialog onClose={closeModal} onDone={refresh} />}
      {modal === "reset" && (
        <ConfirmDialog
          title="Reset demo data"
          message="All patients, appointments and offers will return to their starting state."
          confirmLabel="Reset demo data"
          busy={busy}
          error={actionError}
          onClose={closeModal}
          onConfirm={() => run(api.resetDemo, () => {
            setSelectedSlot(null);
            setPhoneToken(null);
            setNotice(null);
            closeModal();
          })}
        />
      )}
      {cancelSlot?.booking && (
        <ConfirmDialog
          title="Cancel appointment"
          message={`Cancel ${cancelSlot.patient?.name}'s appointment at ${cancelSlot.start} in ${cancelSlot.bay}? They will get a text and the chair will go to standby patients.`}
          confirmLabel="Cancel appointment"
          cancelLabel="Keep appointment"
          busy={busy}
          error={actionError}
          onClose={closeCancel}
          onConfirm={() => {
            const slotId = cancelSlot.slot_id;
            run(() => api.cancelBooking(cancelSlot.booking!.id), () => { setSelectedSlot(slotId); closeCancel(); });
          }}
        />
      )}
    </div>
  );
}
