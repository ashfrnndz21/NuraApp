/** The whole lines the mock backend answers with while #117 is not merged: each step's words,
 *  the read-back lines, the questions, the gap prompts and the close's summary. The headlines,
 *  the "You told us" line, the "more" line and the summary lines follow E01's own English
 *  (`backend/app/onboarding/strings.py`); the rest are stand-ins in the same plain words. English
 *  only. Tagged so `npm run plain-words` holds them to the rules. */

// @patient headline
export const STEP_HEADLINE: Record<string, string> = {
  about_you: "A few things about you",
  papers: "Now, your papers",
  read_back: "Here is what Nura understood",
  questions: "A few questions about your papers",
  closed: "Your app is ready",
};

// @patient
export const STEP_LINES: Record<string, string[]> = {
  about_you: ["Tell Nura which language you like best.", "Tap anything that is part of your health."],
  papers: ["Take a photo of a letter, a blood test or a label.", "Papers from any year are fine."],
  read_back: ["Please say if each line is right."],
  questions: ["Keep the ones to ask the doctor."],
  closed: ["Everything you see is built from this.", "Nura will ask for the rest, one thing a day."],
};

// @patient
export const TOLD = "You told us: {condition}.";

// @patient
export const PAPER_LINE: Record<string, string> = {
  lab_report: "Your blood test is in your papers now.",
  medicine_label: "The medicine label is in your papers now.",
  discharge_letter: "Your hospital letter is in your papers now.",
  clinic_slip: "The appointment card is in your papers now.",
  handwritten_prescription: "The doctor's note is in your papers now.",
  device_screen: "The machine's numbers are in your papers now.",
  insurance_letter: "The insurance letter is in your papers now.",
  other: "One more paper is in your papers now.",
};

// @patient
export const AFTER_NO = "Ask Dr {doctor} to look at that paper again with you.";

// @patient
export const MORE = "{count} more can wait for later.";

// @patient
export const QUESTION: Record<string, string> = {
  medicines: "Ask Dr {doctor} for a list of your medicines.",
  bp_numbers: "Ask Dr {doctor} if you should check at home.",
  weight: "Ask Dr {doctor} how often to weigh yourself.",
  allergy_which: "Ask Dr {doctor} which medicine gives you an allergy.",
  thinner_which: "Ask Dr {doctor} which blood thinner you take.",
  discharge_letter: "Ask Dr {doctor} for a copy of your hospital letter.",
  cholesterol_result: "Ask Dr {doctor} for a newer blood test.",
  sugar_result: "Ask Dr {doctor} for your last sugar test.",
  kidney_result: "Ask Dr {doctor} for your last kidney test.",
  next_visit: "Ask Dr {doctor} when your next visit is.",
  last_visit: "Ask Dr {doctor} what changed at your last visit.",
  insurance: "Ask Dr {doctor} which hospitals take your insurance.",
  meal_times: "Ask Dr {doctor} when to take your tablets.",
  someone_to_see: "Ask Dr {doctor} who else should see your papers.",
};

/** One gap prompt: the fact in his words, what having it lets Nura do, the one action. */
// @patient phrase
export const GAP_HEADLINE: Record<string, string> = {
  medicines: "Which tablets you take, and how much",
  bp_numbers: "Your usual blood pressure numbers",
  weight: "Your weight most mornings",
  allergy_which: "Which medicine gives you an allergy",
  thinner_which: "Which blood thinner you take",
  discharge_letter: "What changed in hospital",
  cholesterol_result: "Your last cholesterol test",
  sugar_result: "Your last sugar test",
  kidney_result: "Your last kidney test",
  next_visit: "Your next visit",
  last_visit: "Your last visit",
  insurance: "Your insurance card",
  meal_times: "Your breakfast time",
  someone_to_see: "Someone who can see your papers",
};

// @patient
export const GAP_LINE: Record<string, string> = {
  medicines: "With it Nura can check each new medicine against the rest.",
  bp_numbers: "With them Nura can say if a number is normal for you.",
  weight: "With it Nura can see water building up early.",
  allergy_which: "With it Nura can put it on your emergency card.",
  thinner_which: "With it Nura can remind you about blood tests.",
  discharge_letter: "With it Nura can check your medicines before and after.",
  cholesterol_result: "With it Nura can show which way it is going.",
  sugar_result: "With it Nura can show what meals do to it.",
  kidney_result: "With it Nura can check new medicines against your kidneys.",
  next_visit: "With it Nura can get your questions ready 3 days before.",
  last_visit: "With it Nura can say what changed since then.",
  insurance: "With it Nura can say which hospitals take your insurance.",
  meal_times: "With it Nura can tie your tablets to your meals.",
  someone_to_see: "With it Nura can tell them if something changes.",
};

// @patient phrase
export const GAP_ACTION: Record<string, string> = {
  medicines: "Take a photo of the medicine bag",
  bp_numbers: "Take a photo of the machine's screen",
  weight: "Take a photo of the scale",
  allergy_which: "Tap which one",
  thinner_which: "Take a photo of the blood thinner",
  discharge_letter: "Take a photo of the hospital letter",
  cholesterol_result: "Add the blood test",
  sugar_result: "Add the sugar test",
  kidney_result: "Add the kidney test",
  next_visit: "Take a photo of the appointment card",
  last_visit: "Take a photo of the last visit's slip",
  insurance: "Take a photo of the insurance card",
  meal_times: "Tap your breakfast time",
  someone_to_see: "Ask one person in",
};

// @patient
export const SUMMARY = {
  papers_none: "No papers were added this time.",
  papers_one: "Nura saved one of your papers.",
  papers_many: "Nura saved {count} of your papers.",
  facts_one: "Nura wrote down one thing from your papers.",
  facts_many: "Nura wrote down {count} things from your papers.",
};
