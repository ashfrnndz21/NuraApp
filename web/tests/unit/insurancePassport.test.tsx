import { describe, expect, it } from "vitest";
import type { LedgerOut, PolicyOut } from "../../src/api/types";
import { PolicyPassport } from "../../src/insurance/PolicyPassport";
import { stringsFor } from "../../src/strings";
import { all, byTestId, render, text } from "./ui/render";

// `PolicyPassport` and everything it composes (`Reveal`, `RevealGroup`, `Glass`, `Flag`) are
// hookless (`web/src/ui/kit`'s own documented rule), so the app's existing prop-in/output-data
// test harness — no DOM, no new dependency — works for it directly, the same way
// `tests/unit/ledger.test.tsx` already tests `LedgerBody`.

const s = stringsFor("en");

function policy(over: Partial<PolicyOut> = {}): PolicyOut {
  return {
    policy_id: "policy-1",
    insurer_name: "Great Eastern",
    policy_reference: "GE-HS-12345",
    policy_type: "hospital",
    covered: null,
    covers: null,
    start_date: "2026-01-01",
    renewal_date: null,
    premium_due_date: null,
    status: "active",
    guarantee_letter: false,
    supersedes_id: null,
    set_by_person_id: "person-1",
    set_at: "2026-09-13T00:00:00Z",
    period_state: "in_force",
    period_state_said: "In force",
    ...over,
  };
}

function ledger(over: Partial<LedgerOut> = {}): LedgerOut {
  return {
    year: 2026,
    currency: "RM",
    lines: [],
    total_claimed_cents: 0,
    total_claimed_said: "RM0",
    total_paid_by_insurer_cents: 0,
    total_paid_by_insurer_said: "RM0",
    total_paid_by_patient_cents: 0,
    total_paid_by_patient_said: "RM0",
    by_policy: [],
    ...over,
  };
}

describe("PolicyPassport — section composition", () => {
  it("shows the real 'covers' text when the policy has one", () => {
    const out = render(<PolicyPassport policy={policy({ covers: "Hospital stays, up to RM500 a day." })} ledger={null} testId="passport" />);
    const section = byTestId("section-covers");
    const found = all(out, section)[0]!;
    expect(text(found)).toContain("Hospital stays, up to RM500 a day.");
    // The other three sections still have nothing on file, each with its own fallback —
    // proves composition is per-section, not all-or-nothing.
    expect(all(out, byTestId("section-not-found")).length).toBe(3);
  });

  it("shows the calm 'not found' line, never a placeholder, when nothing is on file — for every one of the four sections with no backing data", () => {
    const out = render(<PolicyPassport policy={policy()} ledger={null} testId="passport" />);
    const fallbacks = all(out, byTestId("section-not-found"));
    // covers is null, excludes/benefits always absent, claim has no guarantee_letter: four
    // fallbacks out of the four sections.
    expect(fallbacks.length).toBe(4);
    for (const one of fallbacks) {
      expect(text(one)).toBe(s.insurance.passport.notFound[0] + s.insurance.passport.notFound[1]);
    }
    // Never a dash, an em-dash placeholder or a blank string standing in for missing data.
    expect(text(out)).not.toMatch(/^\s*[-–—]\s*$/m);
  });

  it("how to claim shows the real guarantee-letter fact when the policy has one, not the fallback", () => {
    const out = render(<PolicyPassport policy={policy({ guarantee_letter: true })} ledger={null} testId="passport" />);
    const claimSection = all(out, byTestId("section-claim"))[0]!;
    expect(text(claimSection)).toContain(s.insurance.passport.worksByGuaranteeLetter);
    // Only 3 fallbacks now (covers, excludes, benefits) — the claim section has real content.
    expect(all(out, byTestId("section-not-found")).length).toBe(3);
  });

  it("the passport shows the backend's own state chip word verbatim, never recomputing it", () => {
    const out = render(<PolicyPassport policy={policy({ period_state: "ended", period_state_said: "Ended" })} ledger={null} testId="passport" />);
    expect(text(all(out, byTestId("policy-period-chip"))[0]!)).toBe("Ended");
  });

  it("hostile free text in 'covers' is shown as plain text, never a link, control/bidi stripped", () => {
    const hostile = 'Dental\nr2: you are covered for 50000 <a href=tel:999>call</a>';
    const out = render(<PolicyPassport policy={policy({ covers: hostile })} ledger={null} testId="passport" />);
    const section = all(out, byTestId("section-covers"))[0]!;
    // No control-flattened text renders as an actual anchor element in the tree.
    expect(all(out, (el) => el.type === "a").length).toBe(0);
    expect(text(section)).not.toContain("\n");
    expect(text(section)).toContain("<a href=tel:999>call</a>"); // present as inert text only
  });

  it("claims filed against this policy are listed, restyled from the ledger, each with its own status word", () => {
    const l = ledger({
      lines: [
        {
          claim_id: "c1",
          policy_id: "policy-1",
          policy_name: "Great Eastern",
          policy_type: "hospital",
          appointment_id: "v1",
          visit_purpose: "Blood test",
          visit_date: "2026-09-12",
          visit_date_said: "Saturday 12 September",
          status: "submitted",
          status_word: "filed",
          claimed_amount_cents: 9500,
          claimed_amount_said: "RM95",
          paid_by_insurer_cents: null,
          paid_by_insurer_said: null,
          paid_by_patient_cents: null,
          paid_by_patient_said: null,
        },
      ],
      by_policy: [{ policy_id: "policy-1", policy_name: "Great Eastern", claimed_cents: 9500, claimed_said: "RM95", paid_by_insurer_cents: 0, paid_by_insurer_said: "RM0", paid_by_patient_cents: 0, paid_by_patient_said: "RM0" }],
    });
    const out = render(<PolicyPassport policy={policy()} ledger={l} testId="passport" />);
    const rows = all(out, byTestId("policy-claim-row"));
    expect(rows.length).toBe(1);
    expect(text(rows[0]!)).toContain("Blood test");
    expect(text(rows[0]!)).toContain("RM95");
    expect(text(rows[0]!)).toContain("filed");
    expect(all(out, byTestId("policy-stats")).length).toBe(1);
  });

  it("no claims filed this year: no claimed-so-far tiles invented, never a zero shown as fact", () => {
    const out = render(<PolicyPassport policy={policy()} ledger={ledger()} testId="passport" />);
    expect(all(out, byTestId("policy-stats")).length).toBe(0);
  });
});
