import { describe, expect, it } from "vitest";
import type { DigestOut, NudgeMetricsOut, PrivacyOut, ProposalOut, RosterSlotOut } from "../../src/api/familyTypes";
import {
  base64OfBytes,
  digestView,
  fromWallInput,
  inForce,
  markedParts,
  ONLY_ME_PARTS,
  partsOf,
  pushWindow,
  slotRow,
  startOfHisDay,
  toWallInput,
  waiting,
  weekdayNames,
  weekRows,
  wordingLines,
} from "../../src/family/model";

const TEN_AM = Date.parse("2026-09-14T02:00:00Z"); // 10 in the morning, Monday, Singapore

describe("his wall clock", () => {
  it("starts his day at midnight in Singapore, whatever the runner's zone", () => {
    expect(startOfHisDay(TEN_AM)).toBe("2026-09-13T16:00:00.000Z");
    expect(startOfHisDay(TEN_AM, 1)).toBe("2026-09-12T16:00:00.000Z");
    // Half past midnight on his wall is still the new day.
    expect(startOfHisDay(Date.parse("2026-09-14T16:30:00Z"))).toBe("2026-09-14T16:00:00.000Z");
  });

  it("round-trips a datetime-local value with his offset", () => {
    expect(toWallInput(TEN_AM)).toBe("2026-09-14T10:00");
    expect(fromWallInput("2026-09-14T18:30")).toBe("2026-09-14T18:30:00+08:00");
    expect(fromWallInput("not a time")).toBeNull();
  });

  it("puts a message an hour ahead on the quarter, for twelve hours", () => {
    expect(pushWindow(TEN_AM + 7 * 60_000)).toEqual({ sendAt: "2026-09-14T11:15", expiresAt: "2026-09-14T23:15" });
  });

  it("names Monday first, in the reader's language", () => {
    expect(weekdayNames("en-SG")[0]).toMatch(/^Mon/);
    expect(weekdayNames("en-SG")[6]).toMatch(/^Sun/);
  });
});

describe("the family's data", () => {
  it("lists a key's parts without the profile, in the backend's order", () => {
    expect(partsOf(["send", "profile", "medicines", "emergency"])).toEqual(["medicines", "emergency", "send"]);
    expect(ONLY_ME_PARTS).not.toContain("emergency");
  });

  it("makes a roster slot a row of data, never a sentence", () => {
    const slot = { slot_id: "s", person_id: "mei", role: "chief", weekdays: [4, 0, 1], starts_on: null, ends_on: null, from_time: "07:00:00", to_time: "22:00:00", ended_at: null } as RosterSlotOut;
    const row = slotRow(slot, new Map([["mei", "Mei"]]), "en-SG");
    expect(row.who).toBe("Mei");
    expect(row.days.split(" ")).toHaveLength(3);
    expect(row.days).toMatch(/^Mon/);
    expect([row.from, row.to]).toEqual(["07:00", "22:00"]);
  });

  it("keeps the digest in the backend's order, the closing after the entries", () => {
    const digest: DigestOut = {
      language: "en",
      since: "",
      headline: "Pa on Monday 14 September.",
      entries: [{ kind: "message", at: "", lines: ["Mei wrote on Monday 14 September:"], text: "Pa slept well.", message_id: "m" }],
      on_duty: ["Mei"],
      lines: ["Pa on Monday 14 September.", "Mei wrote on Monday 14 September:", "Mei is on duty today."],
    };
    expect(digestView(digest)).toEqual({
      headline: "Pa on Monday 14 September.",
      entries: [{ lines: ["Mei wrote on Monday 14 September:"], text: "Pa slept well." }],
      closing: ["Mei is on duty today."],
    });
  });

  it("shows the agreements in force in their own words, line by line", () => {
    const rows = [
      { consent_id: "a", holder_person_id: null, scopes: null, text_version: "1", wording_text: "Nura keeps your papers.\nThey never leave Singapore.", revoked_at: null },
      { consent_id: "b", holder_person_id: "kit", scopes: ["medicines"], text_version: "2", wording_text: "x", revoked_at: "2026-09-14T02:00:00Z" },
    ];
    expect(inForce(rows).map((row) => row.consent_id)).toEqual(["a"]);
    expect(wordingLines(rows[0]!)).toEqual(["Nura keeps your papers.", "They never leave Singapore."]);
  });

  it("knows which parts are his alone now", () => {
    const rows = [
      { privacy_id: "1", scope: "notes", marked_at: "", lifted_at: null },
      { privacy_id: "2", scope: "money", marked_at: "", lifted_at: "2026-09-14T02:00:00Z" },
    ] as PrivacyOut[];
    expect([...markedParts(rows)]).toEqual(["notes"]);
  });

  it("lists the proposals still waiting, soonest first", () => {
    const one = (id: string, status: ProposalOut["status"], starts_at: string) => ({ proposal_id: id, status, starts_at }) as ProposalOut;
    expect(waiting([one("b", "proposed", "2026-09-20"), one("a", "proposed", "2026-09-18"), one("c", "dismissed", "2026-09-17")]).map((p) => p.proposal_id)).toEqual(["a", "b"]);
  });

  it("gives the week's numbers as counts, newest week first", () => {
    const metrics: NudgeMetricsOut = {
      weeks: [
        { week: "2026-W37", starts_on: "2026-09-07", taps: 5, fine_today: 3, fine_share: 0.6, nudges: {} },
        { week: "2026-W38", starts_on: "2026-09-14", taps: 0, fine_today: 0, fine_share: null, nudges: { visit: { handed_over: 1, accepted: 1, dismissed: 0, seen: 0, ignored: 0, acceptance: 1 } } },
      ],
      ignored_streaks: {},
      resting: [],
      as_of: "",
    };
    const rows = weekRows(metrics);
    expect(rows.map((row) => row.week)).toEqual(["2026-W38", "2026-W37"]);
    expect(rows[1]!.finePercent).toBe(60);
    expect(rows[0]!.finePercent).toBeNull();
    expect(rows[0]!.kinds).toEqual([{ kind: "visit", handedOver: 1, accepted: 1, dismissed: 0 }]);
  });

  it("sends a calendar file as base64", () => {
    const bytes = new TextEncoder().encode("BEGIN:VCALENDAR\nEND:VCALENDAR\n");
    expect(atob(base64OfBytes(bytes.buffer as ArrayBuffer))).toBe("BEGIN:VCALENDAR\nEND:VCALENDAR\n");
  });
});
