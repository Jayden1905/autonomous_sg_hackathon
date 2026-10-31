import { Suspense, useState } from "react";
import {
  Plane,
  X,
  ChevronUp,
  ChevronDown,
  Play,
  Download,
  PanelRightOpen,
  Check,
  AlertTriangle,
  History,
} from "lucide-react";
import { FlightTab } from "@/flight";
import { ScenarioPicker } from "@/scenarios";
import { AirportScene, demoLayout } from "@/airport";
import {
  IconButton,
  DataSection,
  DataRow,
  contextLabel,
  relativeMinutes,
} from "@/workspace";
import type { FlightView, Scenario, Trace, ViewContext } from "@/workspace";
import weather from "../../../scenarios/sample_weather.json";
import noOption from "../../../scenarios/sample_no_legal_option.json";
import recorded from "./traces";

const scenarios: Scenario[] = [weather as Scenario, noOption as Scenario];
const traces = recorded;
type Tab = "Flight" | "Negotiation" | "History";

/** A replaceable integration harness, not a second production shell/store. */
export function Preview() {
  const [scenario, setScenario] = useState<Scenario>(scenarios[0]);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [selectedTurn, setSelectedTurn] = useState<number | null>(null);
  const [selection, setSelection] = useState<FlightView["selection"]>({
    kind: "flight",
    id: scenarios[0].flight,
  });
  const [tab, setTab] = useState<Tab>("Flight");
  const [inspector, setInspector] = useState(() => window.innerWidth >= 900);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [fixture, setFixture] = useState<Trace["outcome"]>("consensus");
  const turn = selectedTurn === null ? null : trace?.turns[selectedTurn];
  const context: ViewContext = turn
    ? "history"
    : (trace?.outcome ?? "scenario");
  const view: FlightView = {
    scenario,
    selection,
    onSelect: (next) => {
      setSelection(next);
      if (next) setInspector(true);
    },
    proposal: turn?.proposal ?? trace?.final ?? null,
    evaluation: turn?.evaluation ?? trace?.final_evaluation ?? null,
    context,
  };
  const chooseScenario = (s: Scenario) => {
    setScenario(s);
    setTrace(null);
    setSelectedTurn(null);
    setSelection({ kind: "flight", id: s.flight });
    setFixture(
      s.scenario_id === noOption.scenario_id ? "no_legal_option" : "consensus",
    );
  };
  const loadFixture = (outcome: Trace["outcome"]) => {
    const next = traces[outcome];
    const s = scenarios.find((s) => s.scenario_id === next.scenario_id)!;
    setScenario(s);
    setTrace(next);
    setSelectedTurn(null);
    setSelection({ kind: "flight", id: s.flight });
    setFixture(outcome);
  };
  const exportTrace = () => {
    if (!trace) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(trace, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `${trace.scenario_id}-${trace.outcome}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <main className="preview">
      <header className="toolbar">
        <div className="brand">
          <Plane size={21} />
          <strong>ATC / Operations</strong>
          <span className="toolbar-divider" />
          <span className="airport-context">
            {scenario.destination} <span>/ Arrival recovery</span>
          </span>
        </div>
        <ScenarioPicker
          scenarios={scenarios}
          selectedId={scenario.scenario_id}
          onSelect={chooseScenario}
        />
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
      <div className="workspace">
        <Suspense
          fallback={
            <div className="loading" role="status">
              Preparing airport…
            </div>
          }
        >
          <AirportScene
            view={view}
            layout={demoLayout}
            inspectorWidth={inspector ? 340 : 0}
          />
        </Suspense>
        {inspector && (
          <aside className="inspector" aria-label="Flight inspector">
            <header className="inspector-heading">
              <div>
                <h1>
                  <Plane size={20} />
                  {scenario.flight}
                </h1>
                <p>
                  {scenario.origin} → {scenario.destination} · Weather
                  disruption
                </p>
              </div>
              <IconButton
                icon={X}
                label="Close flight inspector"
                onClick={() => setInspector(false)}
              />
            </header>
            <div className="tabs" role="tablist" aria-label="Flight details">
              {(["Flight", "Negotiation", "History"] as Tab[]).map((name) => (
                <button
                  key={name}
                  id={`tab-${name}`}
                  role="tab"
                  aria-selected={tab === name}
                  aria-controls={`panel-${name}`}
                  tabIndex={tab === name ? 0 : -1}
                  onClick={() => setTab(name)}
                  onKeyDown={(e) => {
                    const tabs: Tab[] = ["Flight", "Negotiation", "History"];
                    const delta =
                      e.key === "ArrowRight"
                        ? 1
                        : e.key === "ArrowLeft"
                          ? -1
                          : 0;
                    if (delta) {
                      e.preventDefault();
                      const next = tabs[(tabs.indexOf(name) + delta + 3) % 3];
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
              className="inspector-content"
              id={`panel-${tab}`}
              role="tabpanel"
              aria-labelledby={`tab-${tab}`}
              tabIndex={0}
            >
              {tab === "Flight" && <FlightTab {...view} />}
              {tab === "Negotiation" && (
                <>
                  {trace ? (
                    <>
                      <div
                        className={`outcome ${trace.outcome === "consensus" ? "success" : trace.outcome === "fallback" ? "caution" : "failure"}`}
                        role="status"
                      >
                        {trace.outcome === "consensus" ? (
                          <Check size={16} />
                        ) : (
                          <AlertTriangle size={16} />
                        )}
                        <strong>{contextLabel(trace.outcome)}</strong>
                      </div>
                      <DataSection
                        title={
                          trace.outcome === "no_legal_option"
                            ? "Last attempt · not a recommendation"
                            : "Recorded recovery plan"
                        }
                      >
                        <DataRow label="Arrival">
                          {relativeMinutes(trace.final.arrival_min)}
                        </DataRow>
                        <DataRow label="Runway">{trace.final.runway}</DataRow>
                        <DataRow label="Gate">{trace.final.gate}</DataRow>
                      </DataSection>
                      <p>{trace.final.rationale}</p>
                      {trace.fallback_reason && (
                        <p className="muted">{trace.fallback_reason}</p>
                      )}
                      <DataSection title="Recorded rule evaluation">
                        {trace.final_evaluation.results.map((r) => (
                          <details className="rule" key={r.rule}>
                            <summary>
                              <span>{r.rule.replaceAll("_", " ")}</span>
                              <span
                                className={r.passed ? "success" : "failure"}
                              >
                                {r.passed ? "✓ Pass" : "× Fail"}
                              </span>
                            </summary>
                            <p>
                              {r.hard ? "Hard rule" : "Soft rule"} · {r.detail}
                              {r.cost ? ` · Cost ${r.cost}` : ""}
                            </p>
                          </details>
                        ))}
                      </DataSection>
                    </>
                  ) : (
                    <div className="empty">
                      <History size={20} />
                      <h3>No recorded result loaded</h3>
                      <p>
                        Load a bundled mock result to review how the airport and
                        Flight tab respond.
                      </p>
                    </div>
                  )}
                </>
              )}
              {tab === "History" && (
                <>
                  <h3 className="section-title">Recorded turns</h3>
                  {trace ? (
                    <>
                      <p className="muted">{trace.scenario_id}</p>
                      {trace.turns.map((t, i) => (
                        <button
                          className="history-row"
                          key={t.turn}
                          aria-pressed={selectedTurn === i}
                          onClick={() => setSelectedTurn(i)}
                        >
                          <span>
                            Turn {t.turn} · {t.proposer.toUpperCase()}
                          </span>
                          <span>
                            {relativeMinutes(t.proposal.arrival_min)} ·{" "}
                            {t.proposal.gate}
                          </span>
                          <span>
                            {t.evaluation.feasible ? "Feasible" : "Infeasible"}{" "}
                            · Cost {t.evaluation.cost}
                          </span>
                        </button>
                      ))}
                      <button
                        className="text-button"
                        onClick={() => setSelectedTurn(null)}
                      >
                        Back to final result
                      </button>
                    </>
                  ) : (
                    <p className="muted">No recorded turns loaded.</p>
                  )}
                </>
              )}
            </div>
            <footer className="inspector-footer">
              <div>
                <button
                  className="run-button"
                  onClick={() => loadFixture(fixture)}
                >
                  <span>
                    <Play size={15} fill="currentColor" />
                  </span>
                  Load mock result
                </button>
                <IconButton
                  icon={Download}
                  label="Export recorded trace"
                  disabled={!trace}
                  onClick={exportTrace}
                />
              </div>
              <p>Recorded mock agents · Component preview</p>
            </footer>
          </aside>
        )}
        <div className="history-handle">
          <button
            onClick={() => setHistoryOpen(!historyOpen)}
            aria-expanded={historyOpen}
          >
            <History size={14} />
            <span>
              Review states
              {trace
                ? ` · ${trace.turns.length} ${trace.turns.length === 1 ? "turn" : "turns"}`
                : ""}
            </span>
            {historyOpen ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
          {historyOpen && (
            <div className="fixture-list">
              <p>Recorded backend fixtures</p>
              {(["consensus", "fallback", "no_legal_option"] as const).map(
                (outcome) => (
                  <button key={outcome} onClick={() => loadFixture(outcome)}>
                    {contextLabel(outcome)}
                    {trace?.outcome === outcome && <Check size={14} />}
                  </button>
                ),
              )}
              <button onClick={() => chooseScenario(scenario)}>
                Reset to scenario
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
