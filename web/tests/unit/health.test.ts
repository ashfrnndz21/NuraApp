import { describe, expect, it } from "vitest";
import type { FactOut, FoodCatalogItemOut, FoodEntryOut } from "../../src/api/types";
import { bloodPressureRows, bloodSugarRows, foodWords, healthTitle, MEALS, mealsToday, medicinesShown, readingsWithheld } from "../../src/health/model";
import { en } from "../../src/strings/en";

const fact = (over: Partial<FactOut> = {}): FactOut => ({
  fact_id: "f1",
  subject: "blood_pressure",
  attribute: "reading",
  value: { systolic: 132, diastolic: 84 },
  unit: "mmHg",
  valid_from: "2026-09-14T01:00:00Z",
  ...over,
});

const entry = (over: Partial<FoodEntryOut> = {}): FoodEntryOut => ({
  event_id: "e1",
  fact_id: "f1",
  meal: "breakfast",
  meal_label: "Breakfast",
  status: "logged",
  catalog_id: null,
  food: "Rice and fish",
  amount: null,
  eaten_at: "2026-09-14T01:00:00Z",
  ...over,
});

describe("the Health tab's title", () => {
  it("says it in his own words in his density, hers about him by name in hers", () => {
    expect(healthTitle(true, "Ash", en)).toBe("Your health");
    expect(healthTitle(false, "Ash", en)).toBe("Ash's health");
  });
});

describe("the readings block's scope", () => {
  it("is withheld for a key without the readings scope, open for the owner or a key that has it", () => {
    expect(readingsWithheld([])).toBe(true);
    expect(readingsWithheld(["medicines"])).toBe(true);
    expect(readingsWithheld(["readings"])).toBe(false);
    expect(readingsWithheld(["readings", "medicines"])).toBe(false);
  });
});

describe("medicines today", () => {
  it("is shown to the owner always, and to a key whose scope opens medicines", () => {
    expect(medicinesShown(true, [])).toBe(true);
    expect(medicinesShown(false, [])).toBe(false);
    expect(medicinesShown(false, ["medicines"])).toBe(true);
  });
});

describe("his blood pressures and blood sugars", () => {
  it("reads a whole blood pressure off its fact, newest first", () => {
    const rows = bloodPressureRows([
      fact({ fact_id: "a", valid_from: "2026-09-10T01:00:00Z", value: { systolic: 120, diastolic: 78 } }),
      fact({ fact_id: "b", valid_from: "2026-09-14T01:00:00Z", value: { systolic: 132, diastolic: 84 } }),
    ]);
    expect(rows.map((row) => row.words)).toEqual(["132/84", "120/78"]);
  });

  it("leaves out a half reading, and anything not a blood pressure fact", () => {
    expect(bloodPressureRows([fact({ value: { systolic: 130 } }), fact({ subject: "weight", value: { kg: 60 } })])).toEqual([]);
  });

  it("reads his sugar the same way, under its own subject", () => {
    const rows = bloodSugarRows([fact({ subject: "blood_sugar", attribute: "reading", value: { glucose: 6.2 }, valid_from: "2026-09-14T01:00:00Z" })]);
    expect(rows).toEqual([{ at: "2026-09-14T01:00:00Z", words: "6.2" }]);
  });

  it("has nothing to show when nothing has been read, an empty log", () => {
    expect(bloodPressureRows([])).toEqual([]);
    expect(bloodSugarRows([])).toEqual([]);
  });
});

describe("his day's meals (docs/recommendation-engine.md §2.7)", () => {
  const today = new Date("2026-09-14T10:00:00Z");

  it("keeps the latest entry for each meal slot said today", () => {
    const rows = mealsToday(
      [
        entry({ meal: "breakfast", eaten_at: "2026-09-14T00:30:00Z", food: "Toast" }),
        entry({ meal: "breakfast", eaten_at: "2026-09-14T00:45:00Z", food: "Porridge" }),
        entry({ meal: "lunch", eaten_at: "2026-09-13T04:00:00Z", food: "Yesterday's lunch" }),
      ],
      today,
    );
    expect(rows.breakfast?.food).toBe("Porridge");
    expect(rows.lunch).toBeUndefined();
  });

  it("says an answered no as an entry, not a missing one", () => {
    const rows = mealsToday([entry({ meal: "breakfast", status: "skipped", food: null })], today);
    expect(rows.breakfast?.status).toBe("skipped");
  });

  it("is a blank day when nothing was said, never a row of placeholders", () => {
    expect(mealsToday([], today)).toEqual({});
    expect(MEALS.every((meal) => mealsToday([], today)[meal] === undefined)).toBe(true);
  });

  it("shows what he typed, or the catalogue's word for what he tapped, never a bare id", () => {
    const catalog: FoodCatalogItemOut[] = [{ id: "nasi_lemak", label: "Nasi lemak" }];
    expect(foodWords(entry({ food: "Rice and fish" }), catalog)).toBe("Rice and fish");
    expect(foodWords(entry({ food: null, catalog_id: "nasi_lemak" }), catalog)).toBe("Nasi lemak");
    expect(foodWords(entry({ food: null, catalog_id: "unknown_id" }), [])).toBe("unknown_id");
  });
});

describe("the health words are named in all three languages", () => {
  it("has every key filled, en/ms/zh", async () => {
    const { ms } = await import("../../src/strings/ms");
    const { zh } = await import("../../src/strings/zh");
    for (const table of [en, ms, zh]) {
      for (const value of Object.values(table.health)) expect(value).toBeTruthy();
    }
  });
});
