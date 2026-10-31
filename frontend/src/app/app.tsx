import {
  Suspense,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react";
import {
  Plane,
  X,
  Play,
  Download,
  PanelRightOpen,
  History,
  ChevronUp,
  ChevronDown,
} from "lucide-react";
import {
  AirportScene,
  datasetLayout,
  demoLayout,
  stormLayout,
} from "@/airport";
import type { AirportLayout } from "@/airport";
import { FlightTab } from "@/flight";
import { ScenarioPicker } from "@/scenarios";
import { IconButton, contextLabel, Select } from "@/workspace";
import type { FlightView, Scenario, Trace } from "@/workspace";
import { getJson, negotiate } from "@/api";
import type { Schemas } from "@/api";
import {
  NegotiationPanel,
  TurnHistory,
  emptyRun,
  runReducer,
  selectedPlan,
  planComparison,
} from "@/negotiation";
import type { Attempt } from "@/negotiation";

const tabs = ["Flight", "Negotiation", "History"] as const;
type Tab = (typeof tabs)[number];
type SavedRun = { scenario: Scenario; trace: Trace; id: number };
// Explicit presentation anchors per bundled scenario; never inferred from array order.
const layouts: Record<string, AirportLayout> = {
  "sample-weather-ORD": demoLayout,
  "sample-no-legal-option-ORD": demoLayout,
  "demo-storm-ORD-UA599": stormLayout,
  "demo-storm-ORD-VX204-divert": stormLayout,
  "demo-hold-ORD-UA599-decision-time": stormLayout,
};
const unmappedLayout: AirportLayout = { gates: {}, runways: {} };

export function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [health, setHealth] = useState<Schemas["Health"] | null>(null);
  const [connection, setConnection] = useState("Connecting to the API…");
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [datasetLoading, setDatasetLoading] = useState(false);
  const [datasetOffset, setDatasetOffset] = useState(0);
  const [datasetEnd, setDatasetEnd] = useState(false);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetIds, setDatasetIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [state, dispatch] = useReducer(runReducer, undefined, () => emptyRun());
  const [selected, setSelected] = useState<Attempt | null>(null);
  const [selection, setSelection] = useState<FlightView["selection"]>(null);
  const [tab, setTab] = useState<Tab>("Flight");
  const [inspector, setInspector] = useState(() => window.innerWidth >= 900);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [mock, setMock] = useState(true);
  const [maxTurns, setMaxTurns] = useState(3);
  const [effort, setEffort] =
    useState<NonNullable<Schemas["NegotiateRequest"]["effort"]>>("low");
  const [viewport, setViewport] = useState(() => window.innerWidth);
  const runId = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const historyTrigger = useRef<HTMLButtonElement>(null);
  const running = state.status === "running";

  const reset = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    const id = ++runId.current;
    dispatch({ type: "reset", id });
    setSelected(null);
    return id;
  }, []);
  const chooseScenario = useCallback(
    (next: Scenario) => {
      reset();
      setScenario(next);
      setSelection({ kind: "flight", id: next.flight });
    },
    [reset],
  );

  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setLoadError(false);
    Promise.all([
      getJson<Schemas["Health"]>("/health", abort.signal),
      getJson<Schemas["ScenarioSummary"][]>("/scenarios", abort.signal),
    ])
      .then(async ([status, summaries]) => {
        const loaded = await Promise.all(
          summaries.map((s) =>
            getJson<Scenario>(
              `/scenarios/${encodeURIComponent(s.scenario_id)}`,
              abort.signal,
            ),
          ),
        );
        if (abort.signal.aborted) return;
        if (!loaded.length)
          throw new Error("The backend has no bundled scenarios.");
        setHealth(status);
        setScenarios(loaded);
        chooseScenario(
          loaded.find((s) => s.scenario_id === "demo-storm-ORD-UA599") ??
            loaded[0],
        );
        setConnection(
          status.dot_dataset_available
            ? "Backend connected"
            : "Backend connected · Bundled scenarios",
        );
        setDatasetOffset(0);
        setDatasetEnd(false);
        setDatasetError(null);
        setDatasetIds(new Set());
        setLoading(false);
      })
      .catch((error) => {
        if (abort.signal.aborted) return;
        setLoading(false);
        setLoadError(true);
        setConnection(
          error instanceof Error ? error.message : "Backend unavailable",
        );
      });
    return () => abort.abort();
  }, [reload, chooseScenario]);
  useEffect(
    () => () => {
      ++runId.current;
      controller.current?.abort();
    },
    [],
  );
  useEffect(() => {
    const resize = () => setViewport(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  const run = async () => {
    if (!scenario || controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    const id = ++runId.current;
    const snapshot = scenario;
    dispatch({ type: "start", id });
    setSelected(null);
    setTab("Negotiation");
    setInspector(true);
    try {
      await negotiate(
        { scenario: snapshot, mock, max_turns: maxTurns, effort },
        abort.signal,
        (event) => {
          if (id !== runId.current) return;
          if (
            (event.type === "started" || event.type === "done") &&
            event.data.scenario_id !== snapshot.scenario_id
          ) {
            throw new Error(
              "The API returned a different scenario. This run cannot be displayed.",
            );
          }
          dispatch({ type: "event", id, event });
          if (event.type === "done")
            setSaved((previous) =>
              [
                { scenario: snapshot, trace: event.data, id },
                ...previous,
              ].slice(0, 20),
            );
        },
      );
    } catch (error) {
      if (id === runId.current && !abort.signal.aborted)
        dispatch({
          type: "failure",
          id,
          message:
            error instanceof Error ? error.message : "Unable to reach the API.",
        });
    } finally {
      if (id === runId.current) controller.current = null;
    }
  };
  const stopWatching = () => {
    controller.current?.abort();
    controller.current = null;
    dispatch({
      type: "failure",
      id: runId.current,
      message:
        "Stopped watching. The backend may continue this run; no completed result was received.",
    });
    ++runId.current;
  };
  const restore = (entry: SavedRun) => {
    const id = reset();
    setScenario(entry.scenario);
    setSelection({ kind: "flight", id: entry.scenario.flight });
    setScenarios((previous) =>
      previous.some((s) => s.scenario_id === entry.scenario.scenario_id)
        ? previous
        : [...previous, entry.scenario],
    );
    dispatch({ type: "restore", id, trace: entry.trace });
    setTab("Negotiation");
    setInspector(true);
    setHistoryOpen(false);
  };
  const loadDataset = async () => {
    setDatasetLoading(true);
    setDatasetError(null);
    try {
      const more = await getJson<Scenario[]>(
        `/dot/scenarios?offset=${datasetOffset}&limit=20`,
      );
      setScenarios((previous) => [
        ...previous,
        ...more.filter(
          (s) => !previous.some((p) => p.scenario_id === s.scenario_id),
        ),
      ]);
      setDatasetIds(
        (ids) => new Set([...ids, ...more.map((s) => s.scenario_id)]),
      );
      setDatasetOffset((offset) => offset + more.length);
      setDatasetEnd(more.length < 20);
    } catch (error) {
      setDatasetError(
        error instanceof Error
          ? error.message
          : "Unable to load dataset scenarios.",
      );
    } finally {
      setDatasetLoading(false);
    }
  };
  const exportTrace = () => {
    if (!state.trace) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(state.trace, null, 2)], {
        type: "application/json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `${state.trace.scenario_id}-${state.trace.outcome}.json`;
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const inspectAttempt = (attempt: Attempt) => {
    setSelected(attempt);
    setTab("Negotiation");
    setInspector(true);
    setHistoryOpen(false);
  };
  const plan = selectedPlan(state, selected);
  const view: FlightView | null = scenario
    ? {
        scenario,
        proposal: plan.proposal,
        evaluation: plan.evaluation,
        context: plan.context,
        comparison: planComparison(state, selected),
        selection,
        onSelect: (next) => {
          setSelection(next);
          const panel = document.getElementById("panel-Flight");
          if (panel) panel.scrollTop = 0;
          if (next) {
            setInspector(true);
            setTab("Flight");
          }
        },
      }
    : null;
  const announcement = running
    ? state.thinking
      ? `${state.thinking.agent.toUpperCase()} ${state.thinking.action === "propose" ? "proposing" : "evaluating"}, turn ${state.thinking.turn}`
      : "Negotiation running"
    : state.trace
      ? contextLabel(state.trace.outcome)
      : state.status === "error"
        ? "Run incomplete"
        : "";

  return (
    <main className="application">
      <header className="toolbar">
        <div className="brand">
          <Plane size={21} />
          <strong>ATC / Operations</strong>
          <span className="toolbar-divider" />
          <span className="airport-context">
            {scenario?.destination ?? "Airport"} <span>/ Arrival recovery</span>
          </span>
        </div>
        {scenario && (
          <ScenarioPicker
            scenarios={scenarios}
            selectedId={scenario.scenario_id}
            onSelect={chooseScenario}
            status={
              datasetIds.size
                ? `Includes ${datasetIds.size} US DOT flights loaded so far, not the whole dataset.`
                : undefined
            }
          />
        )}
        <div className="toolbar-end">
          <span>Simulation</span>
          <span className="toolbar-divider" />
          <IconButton
            icon={PanelRightOpen}
            label="Open flight inspector"
            onClick={() => setInspector(true)}
          />
        </div>
      </header>
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
      <div className="workspace">
        {view && (
          <Suspense
            fallback={
              <div className="loading" role="status">
                Preparing airport…
              </div>
            }
          >
            <AirportScene
              view={view}
              layout={
                layouts[view.scenario.scenario_id] ??
                (datasetIds.has(view.scenario.scenario_id)
                  ? datasetLayout
                  : unmappedLayout)
              }
              inspectorWidth={
                inspector && viewport >= 900
                  ? viewport >= 1280
                    ? 340
                    : 320
                  : 0
              }
            />
          </Suspense>
        )}
        {(!scenario || loadError) && (
          <div
            className="connection-panel"
            role={loadError ? "alert" : "status"}
          >
            <h1>{loadError ? "Connect the backend" : "Opening workspace"}</h1>
            <p>{loading ? "Loading flight scenarios…" : connection}</p>
            {loadError && (
              <>
                <p>
                  Start the API with <code>make serve</code>, then reconnect.
                </p>
                <button
                  className="text-button"
                  onClick={() => setReload((n) => n + 1)}
                >
                  Reconnect
                </button>
              </>
            )}
          </div>
        )}
        {inspector && view && (
          <aside className="inspector" aria-label="Flight inspector">
            <header className="inspector-heading">
              <div>
                <h1>
                  <Plane size={20} />
                  {view.scenario.flight}
                </h1>
                <p>
                  {view.scenario.origin} → {view.scenario.destination} · Arrival
                  recovery
                </p>
              </div>
              <IconButton
                icon={X}
                label="Close flight inspector"
                onClick={() => setInspector(false)}
              />
            </header>
            <div className="tabs" role="tablist" aria-label="Flight details">
              {tabs.map((name, index) => (
                <button
                  key={name}
                  id={`tab-${name}`}
                  role="tab"
                  aria-selected={tab === name}
                  aria-controls={`panel-${name}`}
                  tabIndex={tab === name ? 0 : -1}
                  onClick={() => setTab(name)}
                  onKeyDown={(event) => {
                    const next =
                      event.key === "ArrowRight"
                        ? tabs[(index + 1) % 3]
                        : event.key === "ArrowLeft"
                          ? tabs[(index + 2) % 3]
                          : event.key === "Home"
                            ? tabs[0]
                            : event.key === "End"
                              ? tabs[2]
                              : null;
                    if (next) {
                      event.preventDefault();
                      setTab(next);
                      document.getElementById(`tab-${next}`)?.focus();
                    }
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
            <div
              key={tab}
              className="inspector-content"
              id={`panel-${tab}`}
              role="tabpanel"
              aria-labelledby={`tab-${tab}`}
              tabIndex={0}
            >
              {tab === "Flight" && <FlightTab {...view} />}
              {tab === "Negotiation" && (
                <NegotiationPanel
                  state={state}
                  selected={selected}
                  onLatest={() => setSelected(null)}
                  onSelect={view.onSelect}
                  scenario={view.scenario}
                />
              )}
              {tab === "History" && (
                <>
                  <p className="muted">{view.scenario.scenario_id}</p>
                  <TurnHistory
                    turns={state.turns}
                    selected={selected}
                    onSelect={inspectAttempt}
                    onLatest={() => setSelected(null)}
                  />
                  <p className="muted">
                    Completed runs are available in Decision history.
                  </p>
                </>
              )}
            </div>
            <footer className="inspector-footer">
              <details className="run-settings">
                <summary>
                  Run settings · {mock ? "Mock agents" : "Live AI"}
                </summary>
                <label>
                  Agent mode
                  <Select
                    label="Agent mode"
                    disabled={running}
                    value={mock ? "mock" : "live"}
                    onChange={(value) => setMock(value === "mock")}
                    options={[
                      {
                        value: "mock",
                        label: "Mock agents",
                        description: "Scripted agents · no model calls",
                      },
                      {
                        value: "live",
                        label: "Live AI",
                        description: "Use the server's model credentials",
                      },
                    ]}
                  />
                </label>
                <label>
                  Maximum turns
                  <Select
                    label="Maximum turns"
                    disabled={running}
                    value={String(maxTurns)}
                    onChange={(value) => setMaxTurns(Number(value))}
                    options={[1, 2, 3, 4, 5, 6].map((n) => ({
                      value: String(n),
                      label: `${n} ${n === 1 ? "turn" : "turns"}`,
                    }))}
                  />
                </label>
                {!mock && (
                  <>
                    <label>
                      Reasoning effort
                      <Select
                        label="Reasoning effort"
                        disabled={running}
                        value={effort}
                        onChange={(value) => setEffort(value as typeof effort)}
                        options={[
                          { value: "low", label: "Low" },
                          { value: "medium", label: "Medium" },
                          { value: "high", label: "High" },
                          { value: "xhigh", label: "Extra high" },
                          { value: "max", label: "Maximum" },
                        ]}
                      />
                    </label>
                    <p>
                      Live AI uses the server’s model credentials and may take
                      several minutes. {health?.default_model}
                    </p>
                    {!health?.sql_tool_available && (
                      <p>
                        Historical metric queries are unavailable on this
                        backend.
                      </p>
                    )}
                  </>
                )}
                {health?.dot_dataset_available ? (
                  <button
                    className="text-button"
                    disabled={datasetLoading || datasetEnd}
                    onClick={loadDataset}
                  >
                    {datasetLoading
                      ? "Loading…"
                      : datasetEnd
                        ? "All dataset scenarios loaded"
                        : "Load 20 more dataset scenarios"}
                  </button>
                ) : (
                  <p>
                    Dataset absent · bundled demo scenarios remain available.
                  </p>
                )}
                {datasetError && <p role="alert">{datasetError}</p>}
                <p>{connection}</p>
              </details>
              <div>
                <button
                  className="run-button"
                  disabled={running || loading || loadError}
                  onClick={run}
                >
                  <span>
                    <Play size={15} fill="currentColor" />
                  </span>
                  {running
                    ? "Negotiating…"
                    : state.status === "error"
                      ? "Retry negotiation"
                      : state.trace
                        ? "Run again"
                        : "Run negotiation"}
                </button>
                <IconButton
                  icon={Download}
                  label="Export negotiation trace"
                  disabled={!state.trace}
                  onClick={exportTrace}
                />
              </div>
              {running ? (
                <p>
                  <button
                    className="text-button stop-watching"
                    onClick={stopWatching}
                  >
                    Stop watching
                  </button>
                  Backend may continue. Switching scenarios also stops watching.
                </p>
              ) : (
                <p>
                  {state.trace
                    ? `Result: ${state.trace.model}`
                    : mock
                      ? "Scripted agents · Backend rule engine"
                      : "Live AI · Simulation, not airport telemetry"}
                </p>
              )}
            </footer>
          </aside>
        )}
        {scenario && (
          <div className="history-handle">
            <button
              ref={historyTrigger}
              onClick={() => setHistoryOpen(!historyOpen)}
              aria-expanded={historyOpen}
              aria-controls="decision-history"
            >
              <History size={14} />
              Decision history{saved.length > 0 && ` · ${saved.length}`}
              {historyOpen ? (
                <ChevronDown size={14} />
              ) : (
                <ChevronUp size={14} />
              )}
            </button>
            {historyOpen && (
              <section
                id="decision-history"
                className="history-drawer"
                aria-label="Decision history"
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setHistoryOpen(false);
                    historyTrigger.current?.focus();
                  }
                }}
              >
                <header>
                  <h2>Decision history</h2>
                  <IconButton
                    icon={X}
                    label="Close decision history"
                    onClick={() => {
                      setHistoryOpen(false);
                      historyTrigger.current?.focus();
                    }}
                  />
                </header>
                <TurnHistory
                  turns={state.turns}
                  selected={selected}
                  onSelect={inspectAttempt}
                  onLatest={() => setSelected(null)}
                />
                <h3>Completed runs</h3>
                <p className="muted">
                  This session · up to 20 runs. Export a trace to keep it.
                </p>
                {saved.length ? (
                  saved.map((entry) => (
                    <button
                      className="history-row"
                      key={entry.id}
                      onClick={() => restore(entry)}
                      disabled={running}
                    >
                      <span>
                        {entry.scenario.flight} ·{" "}
                        {contextLabel(entry.trace.outcome)}
                      </span>
                      <span>
                        {entry.trace.scenario_id} · {entry.trace.model}
                      </span>
                      <span>
                        {new Date(entry.trace.started_at).toLocaleTimeString()}{" "}
                        · {entry.trace.turns.length} turns
                      </span>
                    </button>
                  ))
                ) : (
                  <p className="muted">No completed runs yet.</p>
                )}
              </section>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
