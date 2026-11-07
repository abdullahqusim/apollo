import { randomUUID } from "node:crypto";
import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import express from "express";
import { z } from "zod";

const app = express();
const port = Number(process.env.PORT) || 3000;
// The Python backend behind the console. New calls reach the schedule through its call webhook.
const apolloUrl = process.env.APOLLO_URL || "http://localhost:8000";
const anthropic = new Anthropic();

const TRIAGE_SYSTEM_PROMPT = `You read transcripts of calls to a student dental clinic and pull out what is needed to book the caller an appointment.
Only record what the caller actually said. Use null when something was not said.
Urgency:
- emergency: the caller was told to dial 999 or go to A&E, or has swelling spreading to the neck or eye, trouble breathing, swallowing or speaking, uncontrolled bleeding, chest pain, signs of stroke, a seizure, loss of consciousness, a severe allergic reaction, or thoughts of harming themselves or others
- urgent: needs to be seen as soon as possible, e.g. severe pain, high fever, rapidly worsening symptoms, a child or elderly patient
- soon: should be seen within a few days, e.g. a loose denture or broken crown
- routine: can wait for a normal appointment, or is an administrative query
Availability: the clinic runs Monday to Friday, morning (am) and afternoon (pm). Mark a session false only if the caller ruled it out or limited themselves to other times. If they gave no availability, mark everything true.
Do not diagnose or recommend treatment.`;

const Session = z.object({ am: z.boolean(), pm: z.boolean() });

const Intake = z.object({
  caller_name: z.string().nullable(),
  caller_phone: z.string().nullable().describe("Only if the caller gave a number to reach them on"),
  date_of_birth: z.string().nullable().describe("YYYY-MM-DD if the date is clear, otherwise as the caller said it"),
  caller_words: z.string().describe("Everything the caller said, word for word, leaving out what the agent said"),
  summary: z.string().describe("One or two plain sentences on why they called, for the receptionist"),
  urgency: z.enum(["emergency", "urgent", "soon", "routine"]),
  availability: z.object({
    monday: Session,
    tuesday: Session,
    wednesday: Session,
    thursday: Session,
    friday: Session,
  }),
  short_notice_ok: z.boolean().nullable().describe("Can they come in at short notice if a chair opens up"),
  wants_earlier: z.boolean().nullable().describe("Do they want to be offered an earlier appointment"),
  medical_history: z
    .object({
      conditions: z.array(z.string()),
      allergies: z.array(z.string()),
      medications: z.array(z.string()),
      declined: z.boolean().describe("The caller said they would rather not say"),
    })
    .nullable()
    .describe("null if medical history never came up"),
});

function readIntake(transcript: string) {
  return anthropic.messages.parse({
    model: "claude-haiku-5-5",
    max_tokens: 16000,
    output_config: { effort: "low", format: zodOutputFormat(Intake) },
    system: TRIAGE_SYSTEM_PROMPT,
    messages: [{ role: "user", content: transcript }],
  });
}

type Line = { speaker: "agent" | "patient"; text: string };

const PATIENT_LABELS = /^(patient|caller|user|customer)$/i;

// The backend wants turns. Reads "Agent: ..." / "Patient: ..." lines. An unlabelled transcript mixes both speakers,
// and the agent's own questions would look like symptoms, so it falls back to the caller's words alone.
function toTurns(transcript: string, callerWords: string): Line[] {
  const turns: Line[] = [];
  for (const raw of transcript.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const labelled = line.match(/^([A-Za-z ]{2,20}):\s*(.*)$/);
    if (labelled) {
      turns.push({ speaker: PATIENT_LABELS.test(labelled[1].trim()) ? "patient" : "agent", text: labelled[2] });
    } else if (turns.length) {
      turns[turns.length - 1].text += ` ${line}`;
    } else {
      turns.push({ speaker: "patient", text: line });
    }
  }
  const labelled = turns.some((turn) => turn.speaker === "agent") && turns.some((turn) => turn.speaker === "patient");
  return labelled ? turns : [{ speaker: "patient", text: callerWords }];
}

app.use(express.json());

app.get("/", (_req, res) => {
  res.status(200).json({ status: "ok" });
});

app.post("/triage", async (req, res) => {
  const transcript = req.body?.transcript;
  const callerId = req.body?.caller_phone;

  if (typeof transcript !== "string" || transcript.trim() === "") {
    res.status(400).json({ error: "transcript is required and must be a non-empty string" });
    return;
  }

  let message: Awaited<ReturnType<typeof readIntake>>;
  try {
    message = await readIntake(transcript);
  } catch (error) {
    if (error instanceof Anthropic.APIError) {
      console.error(`Claude API error ${error.status}:`, error.message);
    } else {
      console.error("Claude request failed:", error);
    }
    res.status(502).json({ error: "triage request to Claude failed" });
    return;
  }

  if (message.stop_reason === "refusal") {
    console.error("Claude refused:", message.stop_details);
    res.status(502).json({ error: "Claude declined to triage this transcript" });
    return;
  }
  const intake = message.parsed_output;
  if (!intake) {
    console.error("Claude returned no usable JSON. Stop reason:", message.stop_reason);
    res.status(502).json({ error: "Claude did not return a usable triage" });
    return;
  }

  const phone = intake.caller_phone ?? (typeof callerId === "string" && callerId.trim() ? callerId.trim() : null);
  const history = intake.medical_history;

  let booking: Record<string, unknown>;
  try {
    const response = await fetch(`${apolloUrl}/webhooks/call-ended`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        call_id: typeof req.body?.call_id === "string" ? req.body.call_id : randomUUID(),
        outcome: intake.urgency === "emergency" ? "emergency_redirected" : "intake_completed",
        transcript: toTurns(transcript, intake.caller_words),
        summary: intake.summary,
        caller_name: intake.caller_name,
        caller_phone: phone,
        caller_dob: intake.date_of_birth,
        availability: intake.availability,
        short_notice_ok: intake.short_notice_ok,
        wants_earlier: intake.wants_earlier,
        conditions: history?.conditions,
        allergies: history?.allergies,
        medications: history?.medications,
        history_declined: history?.declined,
        agent_urgency: intake.urgency,
      }),
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${await response.text()}`);
    }
    booking = await response.json();
  } catch (error) {
    console.error("Apollo backend call failed:", error);
    res.status(502).json({ error: "could not send the call to the Apollo backend", intake });
    return;
  }

  res.status(201).json({
    ...intake,
    caller_phone: phone,
    outcome: booking.outcome,
    patient_id: booking.patient_id ?? null,
    case_id: booking.case_id ?? null,
  });
});

app.listen(port, () => {
  console.log(`API listening on http://localhost:${port}`);
});
