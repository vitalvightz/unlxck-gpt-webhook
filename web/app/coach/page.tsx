import { RoleComingSoon } from "@/components/role-coming-soon";
import { useTranslations as useAppTranslations } from "next-intl";

export default function CoachPage() {
    const appText = useAppTranslations("AppText");
  return (
    <RoleComingSoon
      kicker={appText("text_e6b7456c0995")}
      title={appText("text_b38441aeb730")}
      message="Coach accounts will be available in public beta. For now, Unlxck private beta is open to athletes."
    />
  );
}
