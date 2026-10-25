// Real renderer and anonymised saved contact fixture; visible instruction QA.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { CampDayCard, SessionCard } from "../components/structured-plan-renderer.tsx";
const saved = JSON.parse(readFileSync("../tests/fixtures/sparring_contact/production_contact_days.json", "utf8"));
const day = saved.find(day => day.countdown_label === "D-35");
day.today_card.coach_led_contact = "Hard sparring";
// Retain a legacy synthetic dose: prompt-driven reflection must not show a timer.
day.sessions[0].planned_duration = { value: 2, unit: "minutes" };
day.sessions[0].blocks[0].coaching_cues[0] = "2 minutes, RPE 1 max.";
const session = (title, duration, instruction) => ({ session_id: title, title, session_type: "skill",
  planned_duration: { value: duration, unit: "minutes" },
  objective: "Follow the selected scenario. Keep the picture familiar and calm.",
  blocks: [{ block_id: title, display_name: title, duration: { value: duration, unit: "minutes" },
    coaching_cues: [instruction] }] });
process.stdout.write(renderToStaticMarkup(React.createElement(React.Fragment, null,
  React.createElement(CampDayCard, { day, defaultOpen: true }),
  React.createElement(SessionCard, { session: session("Fight Visualisation", 5, "Enter behind your jab, cut off the exit and reset calmly.") }),
  React.createElement(SessionCard, { session: session("Tactical Focus", 7, "Review how your opponent exits after the jab. Choose one adjustment for the next session.") }))));
