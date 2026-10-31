import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import styles from "./workspace.module.css";

export function IconButton({
  icon: Icon,
  label,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: LucideIcon;
  label: string;
}) {
  return (
    <button
      type="button"
      {...props}
      className={`${styles.iconButton} ${props.className ?? ""}`}
      aria-label={label}
      title={label}
    >
      <Icon size={16} strokeWidth={1.5} />
    </button>
  );
}

export function DataRow({
  label,
  children,
  tone,
}: {
  label: string;
  children: ReactNode;
  tone?: "danger";
}) {
  return (
    <div className={styles.row}>
      <dt>{label}</dt>
      <dd className={tone === "danger" ? styles.danger : undefined}>
        {children}
      </dd>
    </div>
  );
}

export function DataSection({
  title,
  children,
  note,
}: {
  title: string;
  children: ReactNode;
  note?: string;
}) {
  return (
    <section className={styles.section}>
      <h3>{title}</h3>
      {note && <p className={styles.note}>{note}</p>}
      <dl>{children}</dl>
    </section>
  );
}
