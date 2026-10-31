import { Radio, Plane, Truck } from "lucide-react";
import { relativeMinutes } from "@/workspace";
import type { Scenario } from "@/workspace";

/**
 * What each organisation can see before anyone talks. This is the reason the
 * negotiation exists: the constraints below are real, but no single party holds
 * all three columns. The agents each get one column; the rule engine sees all.
 */
export function PartyBriefs({ scenario: s }: { scenario: Scenario }) {
  const openRunways = s.runways.filter((r) => r.open && !r.taxiway_blocked);
  const closed = s.runways.filter((r) => !r.open);
  const blocked = s.runways.filter((r) => r.open && r.taxiway_blocked);
  const queue = openRunways.flatMap((r) => r.arrivals ?? []);
  const heavies = queue.filter((a) => a.category === "H").length;
  const margin = s.fuel_endurance_min - s.final_reserve_min;
  const pax = (s.connections ?? []).reduce((n, c) => n + c.passengers, 0);
  const firstBank = (s.connections ?? [])
    .map((c) => c.departs_min)
    .sort((a, b) => a - b)[0];
  const soonestGate = [...s.gates].sort(
    (a, b) => a.free_from_min - b.free_from_min,
  )[0];
  const moves = s.moves ?? [];
  const movesFor = (owner: string) =>
    moves.filter((m) => m.id.startsWith(`${owner}.`));

  return (
    <section className="parties" aria-label="What each party knows">
      <h3>
        Three parties, three views{" "}
        <span className="muted">none sees the others until they talk</span>
      </h3>
      <div className="party-grid">
        <Party icon={<Radio size={14} />} name="Tower" owns="runways & sequence">
          <li>
            {openRunways.length} runway{openRunways.length === 1 ? "" : "s"}{" "}
            open
            {closed.length > 0 && ` · ${closed.map((r) => r.name).join(", ")} closed`}
            {blocked.length > 0 &&
              ` · ${blocked.map((r) => r.name).join(", ")} taxiway blocked`}
          </li>
          <li>
            {queue.length} other arrivals queued, {heavies} heav
            {heavies === 1 ? "y" : "ies"}
          </li>
          <li>Wake spacing by category is non-negotiable</li>
          <Unknown>fuel on board · which gate the airline wants</Unknown>
          <Moves list={movesFor("atc")} />
        </Party>
        <Party icon={<Plane size={14} />} name="Cockpit" owns="fuel & passengers">
          <li>Earliest arrival {relativeMinutes(s.earliest_arrival_min)}</li>
          <li className={margin < 0 ? "failure" : undefined}>
            {margin < 0
              ? `${Math.abs(margin)} min short of final reserve`
              : `${margin} min of holding before final reserve`}
          </li>
          <li>
            {pax} connecting passenger{pax === 1 ? "" : "s"}
            {firstBank !== undefined &&
              `, first bank leaves ${relativeMinutes(firstBank)}`}
          </li>
          <Unknown>gate availability · tower's queue</Unknown>
          <Moves list={movesFor("pilot")} />
        </Party>
        <Party icon={<Truck size={14} />} name="Ramp" owns="gates & crew">
          <li>
            {s.gates.length} gate{s.gates.length === 1 ? "" : "s"}
            {soonestGate &&
              `, ${soonestGate.name} free from ${relativeMinutes(soonestGate.free_from_min)}`}
          </li>
          <li>Crew shift ends {relativeMinutes(s.crew_shift_ends_min)}</li>
          <li>Turnaround {s.turnaround_min} min</li>
          <Unknown>pilot's fuel margin · tower's sequence</Unknown>
          <Moves list={movesFor("ground")} />
        </Party>
      </div>
      <p className="muted">
        Today these three coordinate by phone and radio while the aircraft
        holds. The negotiation lets each agent hold one column and find a plan
        the rule engine accepts.
      </p>
    </section>
  );
}

function Party({
  icon,
  name,
  owns,
  children,
}: {
  icon: React.ReactNode;
  name: string;
  owns: string;
  children: React.ReactNode;
}) {
  return (
    <div className="party">
      <h4>
        {icon} {name} <span className="muted">{owns}</span>
      </h4>
      <ul>{children}</ul>
    </div>
  );
}

function Unknown({ children }: { children: React.ReactNode }) {
  return (
    <li className="party-unknown">
      <span>Can't see:</span> {children}
    </li>
  );
}

function Moves({ list }: { list: Scenario["moves"] }) {
  if (!list?.length) return null;
  return (
    <li className="party-moves">
      <span>Can offer:</span>{" "}
      {list.map((m) => m.label ?? m.id.split(".").slice(1).join(" ")).join(", ")}
    </li>
  );
}
