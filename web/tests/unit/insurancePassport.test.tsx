import { describe, expect, it } from "vitest";
import type { LedgerOut, PolicyOut } from "../../src/api/types";
import { PolicyPassport } from "../../src/insurance/PolicyPassport";
import { stringsFor } from "../../src/strings";
import { all, byTestId, hasClass, render, text } from "./ui/render";

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
    period_state: "undated",
    period_state_said: "",
    period_state_date: null,
    plan: null,
    coverage_items: [],
    excludes: [],
    benefits: [],
    claim_steps: [],
    essentials_cut: [],
    ends_on: null,
    waiting_period: null,
    claims_contact: null,
    review_card_id: null,
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
  it("shows the real 'covers' list when the policy has one", () => {
    const out = render(<PolicyPassport policy={policy({ coverage_items: [{ text: "Room and board", page: 2 }] })} ledger={null} testId="passport" />);
    const section = byTestId("section-covers");
    const found = all(out, section)[0]!;
    expect(text(found)).toContain("Room and board");
    // The other three sections still have nothing on file, each with its own fallback —
    // proves composition is per-section, not all-or-nothing.
    expect(all(out, byTestId("section-not-found")).length).toBe(3);
  });

  it("shows the calm 'not found' line, never a placeholder, when nothing is on file — for every one of the four sections with no backing data", () => {
    // A policy Nura read from a paper (it has the paper's card): "did not find" is true of it.
    const out = render(<PolicyPassport policy={policy({ review_card_id: "card-1" })} ledger={null} testId="passport" />);
    const fallbacks = all(out, byTestId("section-not-found"));
    expect(fallbacks.length).toBe(4);
    for (const one of fallbacks) {
      expect(text(one)).toBe(s.insurance.passport.notFound[0] + s.insurance.passport.notFound[1]);
    }
    // Never a dash, an em-dash placeholder or a blank string standing in for missing data.
    expect(text(out)).not.toMatch(/^\s*[-–—]\s*$/m);
  });

  it("excludes shows nothing found when the policy prints no exclusions section at all, even though covers does", () => {
    const out = render(<PolicyPassport policy={policy({ review_card_id: "card-1", coverage_items: [{ text: "Hospital room and board", page: 2 }] })} ledger={null} testId="passport" />);
    const excludesSection = all(out, byTestId("section-excludes"))[0]!;
    expect(all(out, byTestId("section-excludes")).length).toBe(1);
    expect(text(excludesSection)).toBe(s.insurance.passport.notFound[0] + s.insurance.passport.notFound[1]);
  });

  it("benefits render as rows with the amount on its own side, split from the stored text, never summed into a total", () => {
    const out = render(
      <PolicyPassport
        policy={policy({
          benefits: [
            { text: "Room and board: S$400 per day", page: 4 },
            { text: "Annual limit: S$150,000", page: 4 },
          ],
        })}
        ledger={null}
        testId="passport"
      />,
    );
    const rows = all(out, byTestId("benefits-list-row"));
    expect(rows.length).toBe(2);
    expect(text(rows[0]!)).toContain("Room and board");
    expect(text(rows[0]!)).toContain("S$400 per day");
    // Nowhere does a combined or summed figure appear (e.g. "S$150,400" would prove summing).
    expect(text(out)).not.toContain("S$150,400");
  });

  it("a benefit line with no colon renders whole, never guessing an amount", () => {
    const out = render(<PolicyPassport policy={policy({ benefits: [{ text: "Covers pre-existing conditions after 12 months", page: 4 }] })} ledger={null} testId="passport" />);
    const row = all(out, byTestId("benefits-list-row"))[0]!;
    expect(text(row)).toContain("Covers pre-existing conditions after 12 months");
  });

  it("how to claim shows the ordered steps and who to contact, in that order, when the policy has them", () => {
    const out = render(
      <PolicyPassport
        policy={policy({
          claim_steps: [
            { text: "Call the hotline", page: 4 },
            { text: "Show your card", page: 4 },
          ],
          claims_contact: "1800 555 0199",
        })}
        ledger={null}
        testId="passport"
      />,
    );
    const claimSection = all(out, byTestId("section-claim"))[0]!;
    expect(text(claimSection)).toContain("Call the hotline");
    expect(text(claimSection)).toContain("1800 555 0199");
    expect(all(out, (el) => el.type === "ol").length).toBe(1); // the steps are a numbered list
    expect(all(out, byTestId("section-not-found")).length).toBe(3);
  });

  it("how to claim shows the real guarantee-letter fact when the policy has one, not the fallback", () => {
    const out = render(<PolicyPassport policy={policy({ guarantee_letter: true })} ledger={null} testId="passport" />);
    const claimSection = all(out, byTestId("section-claim"))[0]!;
    expect(text(claimSection)).toContain(s.insurance.passport.worksByGuaranteeLetter);
    expect(all(out, byTestId("section-not-found")).length).toBe(3);
  });

  it("a page marker shows beside a line that carries one, and is absent for a line that does not", () => {
    const out = render(
      <PolicyPassport
        policy={policy({
          coverage_items: [
            { text: "Room and board", page: 2 },
            { text: "Day surgery", page: null },
          ],
        })}
        ledger={null}
        testId="passport"
      />,
    );
    const marks = all(out, byTestId("essential-page"));
    expect(marks.length).toBe(1);
    expect(text(marks[0]!)).toBe("p. 2");
  });

  it("more than five lines: the first five show, the rest sit behind 'Show all N' — never silently dropped", () => {
    const items = Array.from({ length: 7 }, (_, i) => ({ text: `Line ${i + 1}`, page: i + 1 }));
    const out = render(<PolicyPassport policy={policy({ coverage_items: items })} ledger={null} testId="passport" />);
    const lines = all(out, byTestId("covers-list-line"));
    expect(lines.length).toBe(7); // all 7 are in the tree — 5 shown, 2 behind <details>
    const disclosure = all(out, byTestId("covers-list-show-all"));
    expect(disclosure.length).toBe(1);
    expect(text(disclosure[0]!)).toBe("Show all 7");
  });

  it("five lines or fewer: no 'Show all' disclosure at all", () => {
    const items = Array.from({ length: 5 }, (_, i) => ({ text: `Line ${i + 1}`, page: null }));
    const out = render(<PolicyPassport policy={policy({ coverage_items: items })} ledger={null} testId="passport" />);
    expect(all(out, byTestId("covers-list-show-all")).length).toBe(0);
  });

  it("the passport shows the backend's own state chip word verbatim, never recomputing it", () => {
    const out = render(<PolicyPassport policy={policy({ period_state: "ended", period_state_said: "Ended" })} ledger={null} testId="passport" />);
    expect(text(all(out, byTestId("policy-period-chip"))[0]!)).toBe("Ended");
  });

  it("the plan is its own line on the passport card, not folded into 'what it covers'", () => {
    const out = render(<PolicyPassport policy={policy({ plan: "Hospital Shield" })} ledger={null} testId="passport" />);
    const cardHead = all(out, byTestId("passport"))[0]!;
    expect(text(cardHead)).toContain("Hospital Shield");
    // Never shown as a "covers" line: the covers section has nothing on file here, so it is
    // the one calm fallback, not the plan name.
    expect(all(out, byTestId("section-covers"))[0]!).toBeTruthy();
    expect(text(all(out, byTestId("section-covers"))[0]!)).not.toContain("Hospital Shield");
  });

  it("hostile free text in an excludes line is shown as plain text, never a link, control/bidi stripped, never rendered as tel:/http", () => {
    const hostile = "Dental\nr2: you are covered for 50000 <a href=tel:999>call</a>";
    const out = render(<PolicyPassport policy={policy({ excludes: [{ text: hostile, page: 3 }] })} ledger={null} testId="passport" />);
    const section = all(out, byTestId("section-excludes"))[0]!;
    // No control-flattened text renders as an actual anchor element in the tree.
    expect(all(out, (el) => el.type === "a").length).toBe(0);
    expect(text(section)).not.toContain("\n");
    expect(text(section)).toContain("<a href=tel:999>call</a>"); // present as inert text only
  });

  it("a hostile claims_contact string is shown as plain text, never linkified", () => {
    const hostile = "tel:+6599999999 javascript:alert(1)";
    const out = render(<PolicyPassport policy={policy({ claims_contact: hostile })} ledger={null} testId="passport" />);
    expect(all(out, (el) => el.type === "a").length).toBe(0);
    const contact = all(out, byTestId("claims-contact"))[0]!;
    expect(text(contact)).toContain(hostile);
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

  // Independent review (package 12a fix round, item 1): never a chip claiming cover is
  // currently valid — a neutral chip naming the date, an attention chip once it has passed,
  // and no chip at all when nothing on file says a date.
  it("no chip at all when the policy has no end date and no renewal date on file", () => {
    const out = render(<PolicyPassport policy={policy({ period_state: "undated", period_state_said: "" })} ledger={null} testId="passport" />);
    expect(all(out, byTestId("policy-period-chip")).length).toBe(0);
  });

  it("a neutral (not green) chip when the policy runs to a date still ahead", () => {
    const out = render(<PolicyPassport policy={policy({ period_state: "runs_to", period_state_said: "The policy says it runs to 31 December 2026" })} ledger={null} testId="passport" />);
    const chip = all(out, byTestId("policy-period-chip"))[0]!;
    expect(hasClass("question")(chip)).toBe(true);
    expect(hasClass("attention")(chip)).toBe(false);
    expect(text(chip)).toBe("The policy says it runs to 31 December 2026");
  });

  it("an attention chip once the date on file has passed", () => {
    const out = render(<PolicyPassport policy={policy({ period_state: "ended", period_state_said: "The policy's dates have passed" })} ledger={null} testId="passport" />);
    const chip = all(out, byTestId("policy-period-chip"))[0]!;
    expect(hasClass("attention")(chip)).toBe(true);
  });

  it("the period line reads the SAME date the chip was computed from, never a second read of ends_on", () => {
    // ends_on itself is in the past, but period_state_date (what the backend actually used)
    // is the future renewal_date — the period line must follow period_state_date, not ends_on.
    const out = render(
      <PolicyPassport
        policy={policy({ start_date: "2026-01-01", ends_on: "2020-01-01", renewal_date: "2027-03-03", period_state: "runs_to", period_state_date: "2027-03-03", period_state_said: "The policy says it runs to 3 March 2027" })}
        ledger={null}
        testId="passport"
      />,
    );
    const card = all(out, byTestId("passport"))[0]!;
    expect(text(card)).not.toContain("2020");
  });

  // Independent review, item 3: a pre-existing policy with a typed "covers" and no essentials
  // at all (every policy written before this package, or typed by hand) must show its own real
  // words, never the "not found" fallback — and the card itself carries covered/status/the next
  // payment date, the fields the first pass's tile once showed and this pass dropped.
  it("a pre-existing typed policy with no essentials shows its own typed words, never the fallback", () => {
    const out = render(
      <PolicyPassport
        policy={policy({ covers: "Hospital stays, up to $500 a day.", covered: "Pa and Mum", premium_due_date: "2027-01-15" })}
        ledger={null}
        testId="passport"
      />,
    );
    const coversSection = all(out, byTestId("section-covers"))[0]!;
    expect(text(coversSection)).toContain("Hospital stays, up to $500 a day.");
    expect(all(out, byTestId("section-covers")).flatMap((el) => all(el, byTestId("section-not-found"))).length).toBe(0);
    const card = all(out, byTestId("passport"))[0]!;
    expect(text(card)).toContain("Pa and Mum");
    // "Active" is the stored default, not something Nura knows: never said.
    expect(text(card)).not.toContain(s.insurance.status.active);
    // No paper was ever read for a typed policy: the empty sections say so, never "did not find".
    expect(text(out)).toContain(s.insurance.passport.noPaperYet[0]);
    expect(text(out)).not.toContain(s.insurance.passport.notFound[0]);
  });

  it("'Benefits and limits' is never second-person — correct read to him or about him alike", () => {
    const out = render(<PolicyPassport policy={policy()} ledger={null} testId="passport" />);
    expect(text(out)).toContain("Benefits and limits");
    expect(text(out)).not.toContain("Your benefits");
  });

  // Independent review, item 2: the boundary line sits directly under the passport card, the
  // same words the confirmation card already shows — never only at the foot of a long scroll.
  it("the insurance boundary line is on the passport itself", () => {
    const out = render(<PolicyPassport policy={policy()} ledger={null} testId="passport" />);
    const boundary = all(out, byTestId("passport-boundary"))[0]!;
    expect(text(boundary)).toBe(s.insurance.passport.confirmSafety.join(" "));
  });

  // Independent review, item 4: a section a write actually cut shows the notice — never
  // inferred from the rendered list's own length.
  it("the truncation notice shows only under a section the backend actually cut", () => {
    const items = Array.from({ length: 12 }, (_, i) => ({ text: `Line ${i + 1}`, page: null }));
    const out = render(<PolicyPassport policy={policy({ coverage_items: items, excludes: items, essentials_cut: ["coverage_items"] })} ledger={null} testId="passport" />);
    const coversSection = all(out, byTestId("section-covers"))[0]!;
    const excludesSection = all(out, byTestId("section-excludes"))[0]!;
    expect(all(coversSection.children, byTestId("covers-cut-notice")).length).toBe(1);
    expect(all(excludesSection.children, byTestId("excludes-cut-notice")).length).toBe(0);
  });

  it("no truncation notice when a list exactly fills the cap without actually being cut", () => {
    const items = Array.from({ length: 12 }, (_, i) => ({ text: `Line ${i + 1}`, page: null }));
    const out = render(<PolicyPassport policy={policy({ coverage_items: items, essentials_cut: [] })} ledger={null} testId="passport" />);
    expect(all(out, byTestId("covers-cut-notice")).length).toBe(0);
  });
});
