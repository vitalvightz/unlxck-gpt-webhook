// Real renderer and anonymised saved contact fixture; native disclosure layout QA.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { CampDayCard, SessionCard } from "../components/structured-plan-renderer.tsx";
const saved = JSON.parse(readFileSync("../tests/fixtures/sparring_contact/production_contact_days.json", "utf8"));
const day = saved.find(day => day.countdown_label === "D-35");
day.today_card.coach_led_contact = "Hard sparring";
const session = (title, duration) => ({ session_id: title, title, session_type: "skill",
  planned_duration: { value: duration, unit: "minutes" },
  objective: "Follow the selected scenario. Keep the picture familiar and calm.",
  blocks: [{ block_id: title, display_name: title, duration: { value: duration, unit: "minutes" },
    coaching_cues: ["Enter behind your jab, cut off the exit and reset calmly."] }] });
process.stdout.write(renderToStaticMarkup(React.createElement(React.Fragment, null,
  React.createElement(CampDayCard, { day, defaultOpen: true }),
  React.createElement(SessionCard, { session: session("Fight Visualisation", 5) }),
  React.createElement(SessionCard, { session: session("Tactical Focus", 7) }))));
