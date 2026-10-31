import { useId, useRef } from "react";
import { Check, AlertTriangle } from "lucide-react";
import { apiUrl } from "@/api";
import type { Schemas } from "@/api";
import { PlanSummary } from "@/workspace";
import type { Evaluation, Proposal, FlightView } from "@/workspace";

type Evidence = NonNullable<Proposal["evidence"]>[number];
export function safeSourceUrl(value: string | null | undefined) {
  try {
    const url = new URL(value ?? "");
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function CitedText({
  text,
  evidence = [],
}: {
  text: string;
  evidence?: Evidence[];
}) {
  const id = useId();
  const sources = useRef<HTMLDetailsElement>(null);
  if (!text && !evidence.length) return null;
  return (
    <div className="cited-text">
      {text && (
        <p>
          {text.split(/(\[\d+\])/g).map((part, i) => {
            const number = /^\[(\d+)\]$/.exec(part)?.[1];
            const found =
              number && evidence.find((e) => e.id === Number(number));
            return found ? (
              <button
                key={i}
                className="citation-marker"
                aria-label={`Show evidence ${number}`}
                onClick={() => {
                  if (sources.current) sources.current.open = true;
                  document.getElementById(`${id}-${number}`)?.focus();
                }}
              >
                {part}
              </button>
            ) : (
              part
            );
          })}
        </p>
      )}
      {evidence.length > 0 && (
        <details ref={sources} className="disclosure">
          <summary>Evidence · {evidence.length} sources</summary>
          {evidence.map((e, i) => (
            <div
              key={`${e.id}-${i}`}
              id={`${id}-${e.id}`}
              tabIndex={-1}
              className="source-entry"
            >
              <strong>
                [{e.id}] {e.citation?.label ?? e.source}
              </strong>
              <p>{e.claim}</p>
              <p className="muted">{e.citation?.text}</p>
              <span
                className={
                  !e.grounded || e.trust === "low" ? "caution" : "muted"
                }
              >
                {e.grounded ? `${e.trust} trust source` : "Unverified source"}
              </span>
              {safeSourceUrl(e.citation?.url) && (
                <a
                  href={safeSourceUrl(e.citation?.url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open source ↗
                </a>
              )}
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

export function Guardrail({ report }: { report: Proposal["guardrail"] }) {
  if (!report) return null;
  return (
    <details className="disclosure">
      <summary className={report.passed ? "muted" : "failure"}>
        {report.passed
          ? "Citation checks passed"
          : "Reply blocked by citation checks"}{" "}
        · {report.attempts} attempt{report.attempts === 1 ? "" : "s"}
      </summary>
      <p className="muted">
        {report.checked_claims} claims checked. Source trust is not a confidence
        score.
      </p>
      {(report.violations ?? []).map((v, i) => (
        <p key={i}>
          {v.code} · {v.message}
        </p>
      ))}
    </details>
  );
}

export function PlanDetails({
  proposal,
  title,
  comparison,
  onSelect,
}: {
  proposal: Proposal;
  title: string;
  comparison?: FlightView["comparison"];
  onSelect?: FlightView["onSelect"];
}) {
  return (
    <>
      <PlanSummary
        proposal={proposal}
        title={title}
        comparison={comparison}
        onSelect={onSelect}
      />
      <CitedText text={proposal.rationale} evidence={proposal.evidence} />
      <Guardrail report={proposal.guardrail} />
    </>
  );
}

export function Rules({ evaluation }: { evaluation: Evaluation | null }) {
  if (!evaluation)
    return <p className="muted">No rule evaluation available.</p>;
  return (
    <section className="detail-section">
      <h3>Rule evaluation</h3>
      <p className={evaluation.feasible ? "success" : "failure"}>
        {evaluation.feasible
          ? "All hard constraints passed"
          : "Hard constraints failed"}
      </p>
      <p className="muted">
        Soft cost {evaluation.cost.toLocaleString()} · weighted score
      </p>
      {evaluation.results.map((rule, i) => (
        <details className="rule" key={`${rule.rule_id ?? rule.rule}-${i}`}>
          <summary>
            <span>{rule.rule.replaceAll("_", " ")}</span>
            <span
              className={
                rule.passed ? "success" : rule.hard ? "failure" : "caution"
              }
            >
              {rule.passed ? <Check size={13} /> : <AlertTriangle size={13} />}
              {rule.passed ? "Pass" : "Fail"}
            </span>
          </summary>
          <p>
            {rule.hard ? "Hard constraint" : "Soft constraint"} ·{" "}
            {rule.domain.toUpperCase()}
          </p>
          <p>{rule.detail}</p>
          {rule.cost !== 0 && <p>Soft cost: {rule.cost}</p>}
          {rule.rule_id && (
            <a
              href={apiUrl(
                `/semantic/lookup?term=${encodeURIComponent(rule.rule_id)}`,
              )}
              target="_blank"
              rel="noreferrer"
            >
              Rule definition ↗
            </a>
          )}
        </details>
      ))}
    </section>
  );
}

export function ToolActivity({ calls }: { calls: Schemas["ToolCall"][] }) {
  if (!calls.length) return null;
  return (
    <details className="disclosure">
      <summary>Tool activity · {calls.length} calls</summary>
      {calls.map((call, i) => (
        <details key={i} className="disclosure">
          <summary>
            {call.agent.toUpperCase()} · {call.tool.replaceAll("_", " ")}
            {call.is_error ? " · Failed" : ""}
          </summary>
          <p className="muted">
            Step {call.step} · {Math.round(call.duration_ms)} ms
          </p>
          <pre>{JSON.stringify(call.input, null, 2)}</pre>
          {call.sql_result && (
            <div className="table-scroll" tabIndex={0}>
              <table>
                <caption>
                  Query result{call.sql_result.truncated ? " · truncated" : ""}
                </caption>
                <thead>
                  <tr>
                    {call.sql_result.columns.map((c, j) => (
                      <th key={j}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {call.sql_result.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((v, c) => (
                        <td key={c}>{v === null ? "—" : String(v)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {call.sql && (
            <details>
              <summary>Compiled SQL</summary>
              <pre>{call.sql}</pre>
            </details>
          )}
          <details>
            <summary>Tool output</summary>
            <pre>{call.output}</pre>
          </details>
          {(call.model_refs ?? []).map((ref) => (
            <a
              className="model-link"
              key={ref}
              href={apiUrl(
                `/semantic/lookup?term=${encodeURIComponent(ref.includes(":") ? ref.slice(ref.indexOf(":") + 1) : ref)}`,
              )}
              target="_blank"
              rel="noreferrer"
            >
              {ref} ↗
            </a>
          ))}
        </details>
      ))}
    </details>
  );
}
