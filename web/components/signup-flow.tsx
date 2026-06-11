"use client";

import { useState } from "react";

import { AuthForm } from "@/components/auth-form";
import { SignupRoleSelection } from "@/components/signup-role-selection";

// Two-step sign-up: pick a role, then complete the account form. Only athlete is
// selectable today, so the role state is narrowed to "athlete" | null. Coach and
// gym_owner are shown as disabled "Coming soon" cards inside the selection step.
export function SignupFlow() {
  const [selectedRole, setSelectedRole] = useState<"athlete" | null>(null);

  if (selectedRole === null) {
    return <SignupRoleSelection onSelectAthlete={() => setSelectedRole("athlete")} />;
  }

  return (
    <AuthForm mode="signup" role={selectedRole} onChangeRole={() => setSelectedRole(null)} />
  );
}
