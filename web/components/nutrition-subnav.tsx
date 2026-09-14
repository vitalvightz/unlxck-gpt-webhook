"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "@/components/nutrition-pages.module.css";
import { useTranslations as useAppTranslations } from "next-intl";

const LINKS = [
  { href: "/nutrition", label: "Workspace" },
  { href: "/nutrition/bodyweight-log", label: "Bodyweight log" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/nutrition") {
    return pathname === href;
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NutritionSubnav() {
    const appText = useAppTranslations("AppText");
  const pathname = usePathname();

  return (
    <nav className={styles.subnav} aria-label={appText("text_04f9bceeee41")}>
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={`${styles.subnavLink} ${isActive(pathname, link.href) ? styles.subnavLinkActive : ""}`.trim()}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
