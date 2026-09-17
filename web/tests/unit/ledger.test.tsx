import { describe, expect, it } from "vitest";
import { Refused } from "../../src/api/client";
import type { LedgerLineOut, LedgerOut } from "../../src/api/types";
import { LedgerBody } from "../../src/screens/record/Ledger";
import { aboutHim, stringsFor } from "../../src/strings";
import { all, byTestId, render, text } from "./ui/render";

const s = stringsFor("en");

function line(over: Partial<LedgerLineOut> = {}): LedgerLineOut {
  return {
    claim_id: "claim-1",
    policy_id: "policy-1",
    policy_name: "Great Eastern",
    policy_type: "hospital",
    appointment_id: "visit-1",
    visit_purpose: "cardiology",
    visit_date: "2026-09-03",
    visit_date_said: "Thursday 3 September",
    status: "paid",
    status_word: "paid",
    claimed_amount_cents: 42_000,
    claimed_amount_said: "S$420",
    paid_by_insurer_cents: 38_000,
    paid_by_insurer_said: "S$380",
    paid_by_patient_cents: 4_000,
    paid_by_patient_said: "S$40",
    ...over,
  };
}

function ledger(over: Partial<LedgerOut> = {}): LedgerOut {
  return {
    year: 2026,
    currency: "S$",
    lines: [line()],
    total_claimed_cents: 42_000,
    total_claimed_said: "S$420",
    total_paid_by_insurer_cents: 38_000,
    total_paid_by_insurer_said: "S$380",
    total_paid_by_patient_cents: 4_000,
    total_paid_by_patient_said: "S$40",
    by_policy: [
      {
        policy_id: "policy-1",
        policy_name: "Great Eastern",
        claimed_cents: 42_000,
        claimed_said: "S$420",
        paid_by_insurer_cents: 38_000,
        paid_by_insurer_said: "S$380",
        paid_by_patient_cents: 4_000,
        paid_by_patient_said: "S$40",
      },
    ],
    ...over,
  };
}

describe("LedgerBody", () => {
  it("shows the totals and one line a claim, in plain words", () => {
    const body = render(<LedgerBody ledger={ledger()} error={null} s={s} />);
    expect(text(all(body, byTestId("ledger-total-claimed"))[0]!)).toContain("S$420");
    expect(text(all(body, byTestId("ledger-total-insurer"))[0]!)).toContain("S$380");
    expect(text(all(body, byTestId("ledger-total-patient"))[0]!)).toContain("S$40");

    const [claim] = all(body, byTestId("ledger-claim-claim-1"));
    expect(claim).toBeDefined();
    expect(text(claim!)).toContain("cardiology");
    expect(text(claim!)).toContain("S$420");
    expect(text(claim!)).toContain("S$380");
    expect(text(claim!)).toContain("S$40");
    expect(text(claim!)).toContain("Great Eastern");
  });

  it("leaves out a row for an amount not yet known, on a pending claim", () => {
    const pending = line({
      claim_id: "claim-2",
      status: "submitted",
      status_word: "filed",
      paid_by_insurer_cents: null,
      paid_by_insurer_said: null,
      paid_by_patient_cents: null,
      paid_by_patient_said: null,
    });
    const body = render(<LedgerBody ledger={ledger({ lines: [pending] })} error={null} s={s} />);
    expect(all(body, byTestId("ledger-insurer-paid"))).toHaveLength(0);
    expect(all(body, byTestId("ledger-patient-paid"))).toHaveLength(0);
    expect(all(body, byTestId("ledger-claimed"))).toHaveLength(1);
  });

  it("says there are no claims yet, when there are none", () => {
    const body = render(<LedgerBody ledger={ledger({ lines: [] })} error={null} s={s} />);
    expect(text(all(body, byTestId("ledger-none"))[0]!)).toBe(s.record.ledgerNone);
    expect(all(body, byTestId("ledger-lines"))).toHaveLength(0);
  });

  it("says it is kept to him — named — for a caregiver without money, never the generic line", () => {
    const refused = new Refused("OutOfScope", 403, "money");
    const named = aboutHim(s, "Pa");
    const body = render(<LedgerBody ledger={null} error={refused} s={named} />);
    const withheld = all(body, byTestId("ledger-withheld"));
    expect(withheld).toHaveLength(1);
    expect(text(withheld[0]!)).toBe("This is kept to Pa.");
    expect(all(body, byTestId("notice"))).toHaveLength(0);
  });

  it("says it is kept to him — for himself — the same way", () => {
    const refused = new Refused("OutOfScope", 403, "money");
    const body = render(<LedgerBody ledger={null} error={refused} s={s} />);
    expect(text(all(body, byTestId("ledger-withheld"))[0]!)).toBe("This is kept to you.");
  });

  it("falls back to the generic refusal notice for anything other than money's own door", () => {
    const body = render(<LedgerBody ledger={null} error={new Refused("NotFound", 404)} s={s} />);
    expect(all(body, byTestId("ledger-withheld"))).toHaveLength(0);
    expect(all(body, byTestId("notice"))).toHaveLength(1);
  });
});
