import { useEffect, useRef, useState } from "react";
import { Search, ArrowRight, X, Check } from "lucide-react";
import type { Scenario } from "@/workspace";
import { IconButton } from "@/workspace";
import styles from "./scenarios.module.css";

export function ScenarioPicker({
  scenarios,
  selectedId,
  onSelect,
}: {
  scenarios: Scenario[];
  selectedId: string;
  onSelect: (scenario: Scenario) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState("");
  useEffect(() => {
    if (open) {
      dialog.current?.showModal();
      search.current?.focus();
    } else dialog.current?.close();
  }, [open]);
  const close = () => {
    setOpen(false);
    setQuery("");
    trigger.current?.focus();
  };
  const filtered = scenarios.filter((s) =>
    `${s.scenario_id} ${s.flight} ${s.origin} ${s.destination} ${s.disruption}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
  return (
    <>
      <button
        ref={trigger}
        className={styles.trigger}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="Find a flight or scenario"
      >
        <Search size={14} />
        <span>Find a flight or scenario</span>
        <kbd>Search</kbd>
      </button>
      <dialog
        ref={dialog}
        className={styles.dialog}
        aria-labelledby="scenario-title"
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <header>
          <h2 id="scenario-title">Choose a scenario</h2>
          <IconButton icon={X} label="Close scenario picker" onClick={close} />
        </header>
        <label className={styles.search}>
          <Search size={16} />
          <input
            ref={search}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search loaded scenarios"
            aria-label="Search loaded scenarios"
          />
        </label>
        <p className={styles.note}>
          Searching {scenarios.length} loaded scenarios. Times are relative to
          scheduled arrival.
        </p>
        <div className={styles.results}>
          {filtered.length ? (
            filtered.map((s) => (
              <button
                key={s.scenario_id}
                className={styles.result}
                onClick={() => {
                  onSelect(s);
                  close();
                }}
              >
                <span className={styles.identity}>
                  <strong>{s.flight}</strong>
                  <span>
                    {s.origin}
                    <ArrowRight size={12} />
                    {s.destination}
                  </span>
                  {selectedId === s.scenario_id && <Check size={14} />}
                </span>
                <span>{s.disruption}</span>
              </button>
            ))
          ) : (
            <p className={styles.empty}>
              No loaded scenarios match “{query}”. Try a flight or airport code.
            </p>
          )}
        </div>
      </dialog>
    </>
  );
}
