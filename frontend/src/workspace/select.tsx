import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import styles from "./select.module.css";

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
  group?: string;
  meta?: string;
  disabled?: boolean;
}

/** Select-only combobox: focus stays on the trigger while the list is open. */
export function Select({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [placement, setPlacement] = useState({
    left: 0,
    top: 0,
    width: 240,
    maxHeight: 300,
  });
  const search = useRef({ text: "", time: 0 });
  const current = options.find((option) => option.value === value);
  const expanded = open && !disabled;
  const openList = () => {
    const selected = options.findIndex(
      (option) => option.value === value && !option.disabled,
    );
    setActive(
      selected >= 0
        ? selected
        : Math.max(
            0,
            options.findIndex((option) => !option.disabled),
          ),
    );
    search.current.text = "";
    setOpen(true);
  };
  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    setOpen(false);
    trigger.current?.focus();
    if (option.value !== value) onChange(option.value);
  };
  const positionMenu = useCallback(() => {
    if (!trigger.current || !menu.current) return;
    const rect = trigger.current.getBoundingClientRect();
    const viewport = window.visualViewport;
    const x = viewport?.offsetLeft ?? 0,
      y = viewport?.offsetTop ?? 0;
    const width = viewport?.width ?? window.innerWidth;
    const height = viewport?.height ?? window.innerHeight;
    const menuWidth = Math.min(Math.max(rect.width, 240), width - 16);
    const below = y + height - rect.bottom - 14;
    const above = rect.top - y - 14;
    const desired = Math.min(menu.current.scrollHeight, 320);
    const upwards = below < desired && above > below;
    const maxHeight = Math.max(0, Math.min(320, upwards ? above : below));
    setPlacement({
      left: Math.max(x + 8, Math.min(rect.left, x + width - menuWidth - 8)),
      top: upwards
        ? Math.max(y + 8, rect.top - Math.min(desired, maxHeight) - 6)
        : rect.bottom + 6,
      width: menuWidth,
      maxHeight,
    });
  }, []);
  useLayoutEffect(() => {
    if (expanded) positionMenu();
  }, [expanded, options, positionMenu]);
  useEffect(() => {
    if (!expanded) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!trigger.current?.contains(target) && !menu.current?.contains(target))
        setOpen(false);
    };
    const dismiss = () => setOpen(false);
    const scroll = (event: Event) => {
      // Focusing a partly visible trigger can scroll its inspector after the
      // click. Follow that movement instead of immediately closing the menu.
      if (!menu.current?.contains(event.target as Node)) positionMenu();
    };
    const wheel = (event: WheelEvent) => {
      if (!menu.current?.contains(event.target as Node)) dismiss();
    };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("wheel", wheel, { passive: true });
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", dismiss);
    window.visualViewport?.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("wheel", wheel);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", dismiss);
      window.visualViewport?.removeEventListener("resize", dismiss);
    };
  }, [expanded, positionMenu]);
  useEffect(() => {
    const option = document.getElementById(`${id}-${active}`);
    const list = menu.current;
    if (!expanded || !option || !list) return;
    // Scroll only the menu, never its trigger's inspector or the page.
    const item = option.getBoundingClientRect();
    const bounds = list.getBoundingClientRect();
    if (item.top < bounds.top + 5) list.scrollTop -= bounds.top + 5 - item.top;
    else if (item.bottom > bounds.bottom - 5)
      list.scrollTop += item.bottom - bounds.bottom + 5;
  }, [expanded, active, id]);
  const move = (direction: number) => {
    for (let step = 1; step <= options.length; step++) {
      const next =
        (active + direction * step + options.length) % options.length;
      if (!options[next].disabled) {
        setActive(next);
        break;
      }
    }
  };
  return (
    <>
      <button
        ref={trigger}
        type="button"
        role="combobox"
        aria-label={label}
        aria-expanded={expanded}
        aria-haspopup="listbox"
        aria-controls={expanded ? id : undefined}
        aria-activedescendant={expanded ? `${id}-${active}` : undefined}
        className={styles.trigger}
        disabled={disabled || options.length === 0}
        onClick={() => (expanded ? setOpen(false) : openList())}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "Tab") {
            setOpen(false);
            return;
          }
          if (event.key === "Escape" && expanded) {
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
            return;
          }
          if (
            ["ArrowDown", "ArrowUp", "Home", "End", "Enter", " "].includes(
              event.key,
            )
          ) {
            event.preventDefault();
            event.stopPropagation();
            if (!expanded) {
              openList();
              return;
            }
            if (event.key === "Enter" || event.key === " ") choose(active);
            else if (event.key === "ArrowDown" || event.key === "ArrowUp")
              move(event.key === "ArrowDown" ? 1 : -1);
            else {
              const indices = options
                .map((_, i) => i)
                .filter((i) => !options[i].disabled);
              setActive(
                event.key === "Home"
                  ? (indices[0] ?? 0)
                  : (indices.at(-1) ?? 0),
              );
            }
          } else if (
            event.key.length === 1 &&
            !event.ctrlKey &&
            !event.metaKey &&
            !event.altKey
          ) {
            event.preventDefault();
            const now = Date.now();
            const text =
              (now - search.current.time < 600 ? search.current.text : "") +
              event.key.toLowerCase();
            search.current = { text, time: now };
            const term = [...text].every((char) => char === text[0])
              ? text[0]
              : text;
            const start = expanded
              ? active
              : options.findIndex((option) => option.value === value);
            const match = options
              .map((_, i) => (start + 1 + i) % options.length)
              .find(
                (i) =>
                  !options[i].disabled &&
                  options[i].label.toLowerCase().startsWith(term),
              );
            if (!expanded) setOpen(true);
            if (match !== undefined) setActive(match);
          }
        }}
      >
        <span className={styles.value}>
          {current?.label ?? (value || "Select an option")}
        </span>
        {current?.meta && <span className={styles.meta}>{current.meta}</span>}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {expanded &&
        createPortal(
          <div
            ref={menu}
            id={id}
            role="listbox"
            aria-label={label}
            className={styles.menu}
            style={placement}
            onPointerDown={(event) => event.preventDefault()}
          >
            {options.map((option, index) => (
              <div key={option.value}>
                {option.group && option.group !== options[index - 1]?.group && (
                  <div className={styles.group} role="presentation">
                    {option.group}
                  </div>
                )}
                <div
                  id={`${id}-${index}`}
                  role="option"
                  aria-label={option.label}
                  aria-selected={option.value === value}
                  aria-describedby={
                    option.description || option.meta
                      ? `${id}-${index}-detail`
                      : undefined
                  }
                  aria-disabled={option.disabled || undefined}
                  className={styles.option}
                  data-active={index === active}
                  onPointerMove={(event) => {
                    if (!option.disabled && event.pointerType === "mouse")
                      setActive(index);
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    choose(index);
                  }}
                >
                  <span className={styles.check}>
                    {option.value === value && (
                      <Check size={14} aria-hidden="true" />
                    )}
                  </span>
                  <span className={styles.optionText}>
                    <span>{option.label}</span>
                    {option.description && (
                      <small id={`${id}-${index}-detail`}>
                        {option.description}
                      </small>
                    )}
                  </span>
                  {option.meta && (
                    <span
                      id={
                        option.description ? undefined : `${id}-${index}-detail`
                      }
                      className={styles.meta}
                    >
                      {option.meta}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
