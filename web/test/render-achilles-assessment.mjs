// Browser layout fixture renders the actual component with the unit CSS loader.
// Submission interactions are exercised separately in the React DOM unit tests.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AchillesAssessmentForm } from "../components/today/achilles-assessment-form.tsx";

const injury = { id: "fixture-injury", episode_id: "fixture-episode", side: "left", status: "monitoring",
  rehab_decision: { achilles_load_review: { criterion_id: "achilles_restore_load_review_v1", status: "unknown" } } };
process.stdout.write(renderToStaticMarkup(React.createElement(AchillesAssessmentForm,
  { injury, token: "fixture-only", onRefresh: async () => {} })));
