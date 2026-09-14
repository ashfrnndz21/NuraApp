/** The whole lines the mock backend answers with — read-back sentences, the assistant's
 *  prompts, what a paper taught it, the questions a paper raises, the gap cards. English
 *  only: the real backend (E01) owns these words, in three languages, and verifies them as
 *  it writes them. These stand in so the screens can be built, and are tagged so
 *  `npm run plain-words` holds them to the same rules. */

// @patient
export const READ_BACK: Record<string, string> = {
  bp: "You have high blood pressure.",
  bp_meds: "You take tablets for your blood pressure.",
  bp_home: "You check your blood pressure at home.",
  ankles: "Your ankles swell.",
  kidney_chk: "Your doctor watches your kidney number.",
  heart_doc: "You see a heart doctor.",
  stroke_fam: "Someone in your family had a stroke.",
  chol: "Your cholesterol is high.",
  statin: "You take the cholesterol tablet.",
  muscle: "Your muscles hurt.",
  liver: "You have a fatty liver.",
  sugar: "You have diabetes.",
  sugar_tabs: "You take the sugar tablet.",
  insulin: "You take insulin.",
  sugar_home: "You check your sugar at home.",
  feet: "Your feet feel numb.",
  eyes_yr: "You have your eyes checked every year.",
  heart: "Your heart needs care.",
  hf: "Your heart is weak.",
  water_pill: "You take the water pill.",
  weigh: "You weigh yourself.",
  stent: "You have had a stent or a bypass.",
  afib: "Your heartbeat is uneven.",
  breathless: "You get out of breath on the stairs.",
  thinner: "You take a blood thinner.",
  kidney: "Your kidneys need care.",
  swelling: "Your legs swell.",
  dialysis: "You have dialysis.",
  breath: "Your breathing needs care.",
  inhaler: "You use an inhaler.",
  lungs: "Your lungs are weak.",
  snore: "You snore or stop breathing at night.",
  joints: "Your joints hurt.",
  knee: "Your knees hurt.",
  painkill: "You take pain tablets most days.",
  falls: "You had a fall this year.",
  thyroid: "Your thyroid needs care.",
  thy_tabs: "You take the thyroid tablet.",
  stomach: "Your stomach gives you trouble.",
  reflux_tabs: "You take the reflux tablet.",
  ulcer: "You had a stomach ulcer before.",
  sleep: "You find it hard to sleep.",
  sleep_tabs: "You take sleeping tablets.",
  weight: "Your weight is on your mind.",
  weight_jab: "You take a weight injection.",
  diet: "You are trying to lose weight.",
  cancer: "You have had cancer.",
  cancer_tx: "You are in cancer treatment now.",
  cancer_checks: "You go for cancer check-ups only.",
  stroke: "You have had a stroke.",
  eyes: "Your eyes need care.",
  cataract: "Your eyes are cloudy.",
  allergy: "You have allergies.",
  drug_all: "A medicine gives you an allergy.",
  food_all: "A food gives you an allergy.",
  smoke: "You are a smoker.",
  quit: "You stopped smoking.",
  hosp: "You were in hospital last year.",
  dl_have: "You have your hospital letter.",
  meds5: "You take 5 or more medicines.",
  bag: "You can take a photo of the medicine bag.",
  famhx: "Your family has some illnesses.",
  heart_fam: "Someone in your family has heart trouble.",
  sugar_fam: "Someone in your family has diabetes.",
  cancer_fam: "Someone in your family had cancer.",
  memory: "Your memory is on your mind.",
  mem_doc: "You saw a doctor about your memory.",
  mem_worry: "Your family is worried about your memory.",
};

// @patient
export const ANSWERS: Record<string, Record<string, string>> = {
  bp_meds: {
    lt1: "You started them less than a year ago.",
    "1to5": "You have taken them for 1 to 5 years.",
    gt5: "You have taken them for more than 5 years.",
  },
  bp_home: {
    lt130: "Your top number is usually under 130.",
    "130to150": "Your top number is usually 130 to 150.",
    gt150: "Your top number is usually over 150.",
    unsure: "You are not sure what it usually is.",
  },
  heart_doc: {
    "3m": "You see the heart doctor every 3 months.",
    "6m": "You see the heart doctor every 6 months.",
    "1y": "You see the heart doctor every year.",
    need: "You see the heart doctor only when you need to.",
  },
  statin: {
    none: "The tablet does not trouble you.",
    aches: "The tablet makes your muscles ache.",
    unsure: "You are not sure if the tablet troubles you.",
  },
  insulin: { "1": "You take it once a day.", "2": "You take it twice a day.", more: "You take it more than twice a day." },
  stent: { ty: "You had it this year.", "1to5": "You had it 1 to 5 years ago.", longer: "You had it longer ago." },
  thinner: {
    warfarin: "It is warfarin, the one with blood tests.",
    newer: "It is a newer one, with no blood tests.",
    unsure: "You are not sure which kind it is.",
  },
  drug_all: {
    penicillin: "A medicine for infections gives you an allergy.",
    aspirin: "Aspirin gives you an allergy.",
    another: "Another medicine gives you an allergy.",
    unsure: "You are not sure which medicine it is.",
  },
};

// @patient
export const PROMPTS = {
  first: [
    "Thank you for telling Nura.",
    "Now Nura has the shape of things.",
    "Next, Nura would like to see your papers.",
    "Take a photo of a letter, a blood test or a label.",
    "Papers from any year are fine.",
  ],
  next: ["Nura has read that one.", "Do you have another paper to hand?", "A medicine label or a hospital letter helps most."],
  unread: ["Nura could not read that page.", "Try again with the page flat, in daylight."],
  done: ["That is all for now.", "Nura will ask for the rest, one thing a day."],
};

// @patient
export const LEARNED: Record<string, string[]> = {
  lab_report: ["Your blood test is in your papers now.", "Nura can show which way your numbers go."],
  medicine_label: ["The medicine label is in your papers now.", "Nura knows one medicine and how you take it."],
  discharge_letter: ["Your hospital letter is in your papers now.", "Nura knows what changed in hospital."],
  clinic_slip: ["The appointment card is in your papers now.", "Nura knows one of your doctors."],
  handwritten_prescription: ["The doctor's note is in your papers now.", "Nura knows one medicine from it."],
  device_screen: ["The machine's numbers are in your papers now.", "Nura can show which way they go."],
  insurance_letter: ["The insurance letter is in your papers now.", "Nura knows what your insurance covers."],
};

// @patient
export const QUESTIONS = {
  labOld: "Ask Dr {doctor} for a newer blood test.",
  labStatin: "Ask Dr {doctor} if the cholesterol tablet is working.",
  thinnerLabel: "Ask Dr {doctor} when your next blood test is.",
  bpHome: "Ask Dr {doctor} if you should check at home.",
  noPapers: "Ask Dr {doctor} for a copy of your last blood test.",
};

/** One gap card, docs/gaps-and-unlocks.md §1: under the heading "Missing", the fact in his
 *  words; then what having it lets Nura do; then the one action, on the button. */
// @patient phrase
export const GAP_MISSING: Record<string, string> = {
  meds: "Which tablets you take, and how much",
  bpv: "Your usual blood pressure numbers",
  hfw: "Your weight most mornings",
  all: "Which medicine gives you an allergy",
  thin: "Which blood thinner you take",
  dl: "What changed in hospital",
  chol: "Your last cholesterol test",
  sug: "Your last sugar test",
  kid: "Your last kidney test",
  doc: "Your doctor and your next visit",
  ins: "Your insurance card",
  fam: "Someone who can see your papers",
};

// @patient
export const GAP_UNLOCK: Record<string, string> = {
  meds: "With it Nura can check each new medicine against the rest.",
  bpv: "With them Nura can say if a number is normal for you.",
  hfw: "With it Nura can see water building up early.",
  all: "With it Nura can put it on your emergency card.",
  thin: "With it Nura can remind you about blood tests.",
  dl: "With it Nura can check your medicines before and after.",
  chol: "With it Nura can show which way it is going.",
  sug: "With it Nura can show what meals do to it.",
  kid: "With it Nura can check new medicines against your kidneys.",
  doc: "With it Nura can get your questions ready 3 days before.",
  ins: "With it Nura can say which hospitals take your insurance.",
  fam: "With it Nura can tell them if something changes.",
};

// @patient phrase
export const GAP_ACTION: Record<string, string> = {
  meds: "Take a photo of the medicine bag",
  bpv: "Take a photo of the machine's screen",
  hfw: "Take a photo of the scale",
  all: "Tap which one",
  thin: "Tap which kind",
  dl: "Take a photo of the hospital letter",
  chol: "Take a photo of any blood test",
  sug: "Take a photo of any blood test",
  kid: "Take a photo of any blood test",
  doc: "Take a photo of the appointment card",
  ins: "Take a photo of the insurance card",
  fam: "Ask one person in",
};

// @patient
export const SOURCES = {
  told: "From what you told Nura on {date}.",
  paper: "From the paper you added on {date}.",
  plan: "Nura made this from your papers on {date}.",
};
