import Link from "next/link";
import styles from "./training-library-link.module.css";
import { TrainingActionContent } from "./training-action-tile";
import tileStyles from "./training-action-tile.module.css";

export function TrainingLibraryLink({ variant = "compact" }: { variant?: "compact" | "tile" }) {
  return (
    <Link href="/plans/library" className={variant === "tile" ? tileStyles.tile : styles.link} aria-label="Find a Drill">
      {variant === "tile" ? <TrainingActionContent kind="find" /> : <>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      Find a Drill
      </>}
    </Link>
  );
}
