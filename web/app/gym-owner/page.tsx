import { RoleComingSoon } from "@/components/role-coming-soon";
import { useTranslations as useAppTranslations } from "next-intl";

export default function GymOwnerPage() {
    const appText = useAppTranslations("AppText");
  return (
    <RoleComingSoon
      kicker={appText("text_07725718de9d")}
      title={appText("text_3d7e36a1ea37")}
      message="Gym accounts will be available in public beta. For now, Unlxck private beta is open to athletes."
    />
  );
}
