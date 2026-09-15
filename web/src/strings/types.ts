/** The shape every language's catalogue fills. Not a strings file: nothing here is shown.
 *
 *  Every property in `en.ts`, `ms.ts` and `zh.ts` carries a `// @patient [kind]` tag on the
 *  line above it, the contract the backend's verifier reads (`app.safety.plain_words`,
 *  `strings_in_typescript`): `make plain-words` and `npm run plain-words` fail the build on
 *  any line that breaks docs/plain-words.md. Slots are `{name}`-style and filled at run time
 *  by `fill()`, never assembled from pieces. */

export type Language = "en" | "ms" | "zh";

/** Who someone is to the patient: the backend's closed set of codes (`Relationship`). */
export type Relationship = "daughter" | "son" | "spouse" | "sibling" | "grandchild" | "other_family" | "helper" | "friend" | "neighbour" | "other";

export const RELATIONSHIPS: readonly Relationship[] = ["daughter", "son", "spouse", "sibling", "grandchild", "other_family", "helper", "friend", "neighbour", "other"];

export const LANGUAGES: readonly Language[] = ["en", "ms", "zh"];

export interface Strings {
  appName: string;
  /** The demo banner (ADR 0008): a headline, then whole sentences. */
  demo: { banner: string; lines: readonly string[] };
  tabs: { today: string; family: string; me: string };
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
    /** Who the one setting up is to him, as a choice: the label she taps. The code goes to
     *  the backend, which says it to him in his language ("Mei, your daughter, …"). */
    relationships: Record<Relationship, string>;
    pickContact: string;
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
  /** The vertical feed (E21): the pager's name, its section labels, its buttons, and the few
   *  lines it says itself. Every card's own words are the backend's. */
  feed: {
    title: string;
    open: string;
    story: string;
    learning: string;
    ask: string;
    family: string;
    notForMe: string;
    keepGoing: string;
    toTablets: string;
    declined: string;
    declinedToday: string;
    shared: string;
    fromPublisher: string;
    cannotShare: string;
    quiet: string;
    quietSub: string;
    nothingMore: string;
    offlineSub: string;
    askTitle: string;
    askAbout: string;
    askLabel: string;
    askLead: string;
    sourcePapers: string;
    sourceMedicines: string;
    sourceVisits: string;
    askWithheld: string;
    back: string;
    statusHeld: string;
    statusSent: string;
    statusOpened: string;
    statusDismissed: string;
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
    remindersGet: string;
    remindersOn: string;
    remindersStop: string;
    remindersDenied1: string;
    remindersDenied2: string;
  };
  /** The visit day (E05-03, E05-04, E02-05, E03-05): the Visit screen's own lines. The
   *  logistics card, the notice, the words for a no and the post-visit card are the backend's. */
  visit: {
    title: string;
    open: string;
    none: string;
    fromVisit: string;
    onDuty: string;
    driveYes: string;
    start: string;
    keepOpen: string;
    consentLead: string;
    saidYes: string;
    saidNo: string;
    listening: string;
    stop: string;
    saving: string;
    saved: string;
    notHeard: string;
    notHeardSub: string;
    cardLater: string;
    stoppedAway: string;
    keepHeard: string;
    hearClip: string;
    byHandTitle: string;
    byHandLabel: string;
    byHandSave: string;
    noMic: string;
    noMicSub: string;
    noConnection: string;
    sendLater: string;
  };
  /** The patient's day (W7): the not-feeling-well button, the symptom log, the nudge's two
   *  buttons, the brief, the questions and the post-visit card's yes. Every card's own lines
   *  are the backend's; `fallback` is the backend's offline card, word for word, for a phone
   *  that kept no copy of it (app/channels/safety_strings.py). */
  day: {
    topThree: string;
    notWell: string;
    notWellTitle: string;
    notWellLead: string;
    wordsLabel: string;
    send: string;
    sayIt: string;
    stopAndSend: string;
    sending: string;
    whatToDo: string;
    backToday: string;
    symptomsOpen: string;
    symptomsTitleSelf: string;
    symptomsTitleOther: string;
    symptomsLead: string;
    symptomsKeep: string;
    sendAgain: string;
    symptomsSaved: string;
    nudgeOk: string;
    nudgeWentWell: string;
    nudgeNotToday: string;
    briefOpen: string;
    briefTitle: string;
    questionsOpen: string;
    questionsTitle: string;
    questionLabel: string;
    questionAdd: string;
    questionCheck: string;
    questionYes: string;
    questionRemove: string;
    questionRemoveCheck: string;
    questionRemoveYes: string;
    questionKept: string;
    questionRemoved: string;
    summaryLead: string;
    summaryLeaveOut: string;
    summaryLeftOut: string;
    summaryFromNotes: string;
    summaryYes: string;
    summaryKept: string;
    summaryWaiting: string;
    fallback: {
      youDidRight: string;
      notSent: string;
      call995: string;
      call999: string;
      callFamily: string;
      bad995: string;
      bad999: string;
      closing: string;
    };
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
      /** One question per settings switch (#117), for his own papers and in the name of someone else's. */
      switchSelf: Record<"large_text" | "high_contrast" | "voice_on" | "big_targets" | "one_thing_per_screen" | "read_back" | "repeat_prompts", string>;
      switchOther: Record<"large_text" | "high_contrast" | "voice_on" | "big_targets" | "one_thing_per_screen" | "read_back" | "repeat_prompts", string>;
      densitySelf: string;
      densityOther: string;
      densitySimple: string;
      densityDetailed: string;
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
      allPapers: string;
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
      /** Who the person let in is to him, as a choice; the code goes to the backend. */
      relationships: Record<Relationship, string>;
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
  /** Family (W6): chrome only. Every line about his record on these screens is the backend's. */
  family: {
    title: string;
    circleSelf: string;
    circleOther: string;
    trailSelf: string;
    trailOther: string;
    onlyMe: string;
    onlyMeLead: string;
    onlyMeYes: string;
    onlyMeLift: string;
    onlyMeMarked: string;
    consentsSelf: string;
    consentsOther: string;
    stop: string;
    stopYes: string;
    howToStop: string;
    keepCopy: string;
    savePage: string;
    thread: string;
    threadEarlier: string;
    messageLabel: string;
    sendMessage: string;
    keys: string;
    newKey: string;
    holderName: string;
    holderPhone: string;
    roleLabel: string;
    partsLabel: string;
    windowLabel: string;
    makeKey: string;
    narrow: string;
    narrowYes: string;
    closeKey: string;
    closeYes: string;
    notNow: string;
    roles: Record<"chief" | "caregiver" | "viewer" | "helper" | "emergency" | "clinic", string>;
    windows: Record<"always" | "thirty_days" | "seventy_two_hours" | "one_day", string>;
    parts: Record<"medicines" | "visits" | "readings" | "records" | "notes" | "money" | "emergency" | "family" | "ask" | "send", string>;
    roster: string;
    rosterTitle: string;
    who: string;
    days: string;
    from: string;
    to: string;
    onDutyNow: string;
    takeOff: string;
    addSlot: string;
    tasksTitle: string;
    taskWhat: string;
    taskDue: string;
    addTask: string;
    done: string;
    doneChip: string;
    nextVisit: string;
    messagesTitle: string;
    templates: Record<"pickup" | "call_you" | "see_doctor" | "thinking_of_you" | "weigh_tomorrow" | "drink_water" | "water_pill_morning", string>;
    ownWords: string;
    slots: Record<"who" | "when" | "doctor" | "day", string>;
    memoLabel: string;
    languageLabel: string;
    preview: string;
    sendAt: string;
    until: string;
    channelApp: string;
    channelWhatsapp: string;
    schedule: string;
    states: Record<"scheduled" | "sent" | "not_sent", string>;
    metrics: string;
    weekOf: string;
    taps: string;
    fineToday: string;
    fineShare: string;
    kind: string;
    handedOver: string;
    accepted: string;
    dismissed: string;
    kinds: Record<"anticipation" | "check_in" | "pattern" | "commitment" | "recognition" | "presence", string>;
    calendar: string;
    chooseFile: string;
    agree: string;
    bookYes: string;
    notThis: string;
    ladderYes: string;
    deliveries: string;
    settings: string;
    triggers: Record<"morning" | "dose" | "reorder" | "doses_untapped" | "flag" | "visit_tomorrow" | "papers" | "family_message" | "first_week_prompt" | "nudge" | "check_in" | "family_notice", string>;
    channels: Record<"app_push" | "whatsapp" | "caregiver", string>;
    outcomes: Record<"sent" | "capped" | "quiet" | "no_channel" | "no_scope" | "skipped", string>;
    /** Why a message was held, where it was not a quiet day: said instead of the outcome, with
     *  `{name}` his (E11-01). Keyed by `HELD_BECAUSE` in `screens/family/Delivery.tsx`. */
    skippedBecause: Record<"flagOpen" | "saidToday" | "nudgeAsked" | "questionOpen", string>;
    rule: string;
    quietFrom: string;
    quietUntil: string;
    skipQuietDays: string;
    cap: string;
    saveSettings: string;
    neverHeld: string;
    documents: string;
    tags: Record<"lpa" | "medical_letter" | "consent_form", string>;
    backs: Record<"consent" | "stewardship", string>;
    stillOn: string;
    stoppedChip: string;
    addDocument: string;
    chooseDocument: string;
    whatPaper: string;
  };
  /** The pharmacist's review queue (E22-04): a staff page, never linked from the patient app. */
  review: {
    title: string;
    tokenLabel: string;
    open: string;
    statusTitle: string;
    cardType: string;
    sampled: string;
    pending: string;
    stillToCheck: string;
    sourcesWaiting: string;
    queueTitle: string;
    showPending: string;
    showAll: string;
    approve: string;
    reject: string;
    reasonLabel: string;
    rewrite: string;
    headline: string;
    body: string;
    voice: string;
    why: string;
    saveRewrite: string;
    decided: string;
    leave: string;
  };
  errors: { network: string; tryAgain: string };
  /** One line per refusal, or two when the second says what to do next; each line one idea. */
  refusals: Record<string, string | readonly string[]> & { default: string };
}
