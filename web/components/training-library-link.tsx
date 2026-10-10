import Link from "next/link";
import styles from "./training-library-link.module.css";

export function TrainingLibraryLink() {
  return (
    <Link href="/plans/library" className={styles.link}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      Find a Drill
    </Link>
  );
}
