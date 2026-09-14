/** The shape every language's catalogue fills. Not a strings file: nothing here is shown.
 *
 *  Every property in `en.ts`, `ms.ts` and `zh.ts` carries a `// @patient [kind]` tag on the
 *  line above it, the contract the backend's verifier reads (`app.safety.plain_words`,
 *  `strings_in_typescript`): `make plain-words` and `npm run plain-words` fail the build on
 *  any line that breaks docs/plain-words.md. Slots are `{name}`-style and filled at run time
 *  by `fill()`, never assembled from pieces. */

export type Language = "en" | "ms" | "zh";

export const LANGUAGES: readonly Language[] = ["en", "ms", "zh"];

export interface Strings {
  appName: string;
  tabs: { today: string; me: string };
  signIn: {
    title: string;
    phoneLead: string;
    phoneHint: string;
    nameLead: string;
    phoneLabel: string;
    nameLabel: string;
    sendCode: string;
    useEmail: string;
    usePhone: string;
    codeLead: string;
    codeHint: string;
    codeWorks: string;
    codeLabel: string;
    signInButton: string;
    emailLead: string;
    emailLabel: string;
    sendLink: string;
    linkLead: string;
    linkHint: string;
    linkLabel: string;
    never: string;
    back: string;
  };
  doors: {
    title: string;
    forMe: string;
    forMeLine: string;
    forSomeone: string;
    forSomeoneLine: string;
    invited: string;
    invitedLine: string;
    waiting: string;
    waitingLine: string;
  };
  consent: { title: string; lead: string; agree: string; language: string };
  claim: { title: string; setUpBy: string; keepsSeeing: string; mine: string };
  forSomeone: {
    title: string;
    lead: string;
    theirName: string;
    theirPhone: string;
    relationshipLabel: string;
    asked: string;
    create: string;
  };
  switcher: {
    title: string;
    own: string;
    roleOwner: string;
    roleChief: string;
    roleCaregiver: string;
    roleSteward: string;
    roleOther: string;
  };
  today: {
    now: string;
    forYou: string;
    greetingMorning: string;
    greetingAfternoon: string;
    greetingEvening: string;
    taken: string;
    tookMorning: string;
    tookAfternoon: string;
    tookEvening: string;
    tookNight: string;
    allTaken: string;
    allTakenSub: string;
    nothingNow: string;
    noMedicines: string;
    noMedicinesSub: string;
    hear: string;
    readingTitle: string;
    readingLead: string;
    readingButton: string;
    readingLeadEvening: string;
    aTablet: string;
    earlierTitle: string;
    stateStable: string;
    stateWatch: string;
    stateWatchSub: string;
    stateAct: string;
    stateActSub: string;
    staleState: string;
    callChief: string;
    callFamily: string;
    proud: string;
    proudOne: string;
    proudNone: string;
    proudSub: string;
    supplyTitle: string;
    todayList: string;
    offline: string;
    offlineSub: string;
    asOf: string;
    cannotReach: string;
    emergencyTitle: string;
    emergencySoon: string;
    homeScreen1: string;
    homeScreen2: string;
    homeScreen3: string;
    fromToday: string;
    fromState: string;
    fromDays: string;
  };
  reading: {
    title: string;
    lead: string;
    top: string;
    bottom: string;
    save: string;
    saved: string;
    cancel: string;
  };
  me: {
    title: string;
    signedInAs: string;
    language: string;
    en: string;
    ms: string;
    zh: string;
    look: string;
    patient: string;
    caregiver: string;
    lookAuto: string;
    switchProfile: string;
    setUp: string;
    signOut: string;
  };
  onboarding: {
    next: string;
    notNow: string;
    later: string;
    back: string;
    saving: string;
    about: {
      titleSelf: string;
      titleOther: string;
      leadSelf: string;
      leadOther: string;
      nameSelf: string;
      nameOther: string;
      nameLabel: string;
      languageSelf: string;
      languageOther: string;
      bornSelf: string;
      bornOther: string;
      decade: string;
      doctorSelf: string;
      doctorOther: string;
      doctorLabel: string;
      doctorHint: string;
      breakfastSelf: string;
      breakfastOther: string;
      breakfastHint: string;
      /** One whole phrase per breakfast time the About step offers (`onboarding/about.ts`). */
      times: Record<"06:00" | "06:30" | "07:00" | "07:30" | "08:00" | "08:30" | "09:00" | "10:00", string>;
      sightSelf: string;
      sightOther: string;
      hearingSelf: string;
      hearingOther: string;
      handsSelf: string;
      handsOther: string;
      memorySelf: string;
      memoryOther: string;
      yes: string;
      no: string;
    };
    cloud: {
      titleSelf: string;
      titleOther: string;
      lead: string;
      lead2: string;
      lead3: string;
      noted: string;
      removed: string;
      more: string;
      fewer: string;
      done: string;
      term: string;
    };
    asks: { lead: string };
    readBack: {
      title: string;
      lead: string;
      lineOf: string;
      yes: string;
      no: string;
      agreed: string;
      disputed: string;
      nothing: string;
      nothingFine: string;
      nothingSub: string;
    };
    records: {
      titleSelf: string;
      titleOther: string;
      photo: string;
      file: string;
      allDone: string;
      looking: string;
      reviewTitle: string;
      reviewLead: string;
      reviewLead2: string;
      sure: string;
      check: string;
      changeLabel: string;
      notANumber: string;
      cannotChange: string;
      leaveOut: string;
      keepIn: string;
      leftOut: string;
      looksRight: string;
      saved: string;
      learnedTitle: string;
      kindLabReport: string;
      kindMedicineLabel: string;
      kindDischargeLetter: string;
      kindClinicSlip: string;
      kindUnknown: string;
      unknownHint: string;
      dated: string;
      highRisk: string;
      fromPhoto: string;
      otherLine: string;
      kindHandwritten: string;
      kindInsuranceLetter: string;
      kindDeviceScreen: string;
      unreadable: string;
      typeIt: string;
    };
    questions: {
      titleSelf: string;
      titleOther: string;
      lead: string;
      keep: string;
      notThis: string;
      kept: string;
      dropped: string;
      none: string;
    };
    invite: {
      title: string;
      lead: string;
      nameLabel: string;
      phoneLabel: string;
      relationshipLabel: string;
      partsLead: string;
      parts: Record<"medicines" | "visits" | "readings" | "records", string>;
      seeWords: string;
      wordsLead: string;
      agree: string;
      done: string;
    };
    plan: {
      title: string;
      lead: string;
      cadence1: string;
      cadence2: string;
      missing: string;
      onDay: string;
      later: string;
      laterSaid: string;
      moreOne: string;
      more: string;
      nothing: string;
      open: string;
    };
    /** His words for a paper's lines, by the backend's subject then attribute code. */
    fields: Record<string, Record<string, string>>;
  };
  errors: { network: string; tryAgain: string };
  /** One line per refusal, or two when the second says what to do next; each line one idea. */
  refusals: Record<string, string | readonly string[]> & { default: string };
}
