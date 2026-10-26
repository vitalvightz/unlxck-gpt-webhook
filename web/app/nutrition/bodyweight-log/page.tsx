import { redirect } from "next/navigation";

// The bodyweight log is now the whole Nutrition page; keep old links working.
export default function BodyweightLogPage() {
  redirect("/nutrition");
}
