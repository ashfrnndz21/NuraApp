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
  demo: { banner: string; bannerShort: string; lines: readonly string[] };
  tabs: { today: string; record: string; family: string; me: string; home: string; medicines: string; records: string; visits: string; timeline: string; plan: string; health: string; connect: string; services: string; profile: string };
  /** The shell (D1): the ask bar on top of Today and Home, its voice button, the sheet's Close;
   *  the header's bell, which opens what is new for him (docs/design-direction.md). */
  shell: { askNura: string; askAbout: string; voice: string; voiceSaid1: string; voiceSaid2: string; close: string; bell: string };
  /** The welcome screen before sign-in (docs/design-direction.md, Reference B's first screen):
   *  a two-line tagline, the line under it, three value tiles, Get started and Sign in. */
  welcome: {
    tagline1: string;
    tagline2: string;
    lead: string;
    remember: string;
    rememberLine: string;
    share: string;
    shareLine: string;
    prepare: string;
    prepareLine: string;
    start: string;
  };
  /** Conversation and waiting (docs/design-direction.md): the words every ask, search and
   *  message composer uses while Nura works. The steps themselves are the backend's lines. */
  talk: { you: string; nura: string; working: string; answered: string; lookedAt: string; slow: string; failed: string; tryAgain: string; loading: string };
  /** Home in the warm style: the question under the greeting, the daily check-in, the grid of
   *  places, adding a health report, and what is coming up. `…Other`: said about him by name. */
  hub: {
    howFeeling: string; howFeelingOther: string;
    checkTitle: string; checkTitleOther: string;
    checkLine: string; checkLineOther: string;
    checkIn: string;
    doTitle: string; doTitleOther: string;
    health: string;
    healthLine: string; healthLineOther: string;
    medicines: string;
    medicinesLine: string; medicinesLineOther: string;
    connect: string;
    connectLine: string; connectLineOther: string;
    activities: string;
    activitiesLine: string;
    care: string;
    careLine: string; careLineOther: string;
    resources: string;
    resourcesLine: string;
    report: string;
    reportLine: string; reportLineOther: string;
    reportNote: string; reportNoteOther: string;
    /** Before the file he picked goes: its name (raw, not this line) plus this line, and the
     *  "Send it" button — his one yes, so a chosen file is never sent on its own. */
    reportReady: string;
    reportReadyOther: string;
    reportSend: string;
    upcoming: string;
    seeAll: string;
    seeAllVisits: string;
    soonLine1: string;
    soonLine2: string;
    backHome: string; backHomeOther: string;
  };
  /** The chief's Home (D1): the hero's label and the tiles' headings. Every line in them is the backend's. */
  home: { mostLikely: string; whatChanged: string; nextVisit: string; atTime: string; buyMore: string; missing: string; missingSub: string; missingSubDay: string; bpLabel: string; fromName: string; showAll: string; showFewer: string; bpLast: string };
  /** The tabs' own titles (D1). */
  places: {
    visitsOwn: string; visitsOwnOther: string;
    visitsOther: string;
    visitsNoneOther: string;
    planTitle: string;
    planLead: string;
  };
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
    lookAgain: string;
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
    openOwn: string;
    openOther: string;
    onlyThese: string;
    cannotLook: string;
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
    readingTitleOther: string;
    readingLead: string;
    readingButton: string;
    readingLeadEvening: string;
    aTablet: string;
    earlierTitle: string;
    stateStable: string; stateStableOther: string; stateWatchOther: string; callFamilyOther: string; offlineSubOther: string; asOfOther: string; cannotReachOther: string; emergencySoonOther: string; todayListOther: string; fromTodayOther: string; tookMorningOther: string; allTakenOther: string;
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
    emergencyOpen: string;
    emergencyOpenOther: string;
  };
  /** The vertical feed (E21): the pager's name, its section labels, its buttons, and the few
   *  lines it says itself. Every card's own words are the backend's. */
  feed: {
    title: string; empty: string; emptyAction: string;
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
    askThinking: string;
    askAnswered: string;
    askLookedAt: string;
    back: string;
    statusHeld: string;
    statusSent: string;
    statusOpened: string;
    statusPlayed: string;
    statusDismissed: string;
    play: string;
    watchWhole: string;
    askOrSearch: string;
    filterLabel: string;
    filterRecords: string;
    filterWeb: string;
    filterProviders: string;
    filterVideos: string;
    search: string;
    readPage: string;
    foundNothing: string;
    nextVisit: string;
  };
  reading: {
    title: string;
    titleOther: string;
    lead: string;
    top: string;
    bottom: string;
    save: string;
    saved: string;
    cancel: string;
    photo: string;
    photoLead: string;
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
    emergencyPrint: string;
    remindersOn: string;
    remindersStop: string;
    remindersDenied1: string;
    remindersDenied2: string;
    areaTitle: string;
    areaLead: string;
    areaNone: string;
    areaIs: string;
    areaAsk: string;
    areaYes: string;
    areaNo: string;
    areaChange: string;
    areaClear: string;
    areaWho: string;
    ramadanTitle: string;
    ramadanLead: string;
    ramadanWho: string;
    ramadanYes: string;
    ramadanOn: string;
    ramadanStop: string;
    whatNuraUsesTitle: string;
    whatNuraUsesLead: string;
    whatNuraUsesLeadOther: string;
    whatNuraUsesOn: string;
    whatNuraUsesOff: string;
    whatNuraUsesReadOnly: string;
    whatNuraUsesFamilies: Record<"food" | "sleep" | "steps" | "water" | "search_topics", string>;
    whatNuraUsesFamiliesOther: Record<"food" | "sleep" | "steps" | "water" | "search_topics", string>;
  };
  /** The visit day (E05-03, E05-04, E02-05, E03-05): the Visit screen's own lines. The
   *  logistics card, the notice, the words for a no and the post-visit card are the backend's. */
  visit: {
    title: string;
    open: string;
    openOther: string;
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
    keepOpenToSend: string;
  };
  /** Taps made while the phone could not reach Nura (E00-08): held, then sent once. */
  held: { held: string; tapped: string; sent: string };
  /** The emergency card on the phone (E00-08, E13-01): the card's lines are the backend's. */
  emergency: { asOf: string; none: string; noneSub: string; callChief: string; callAmbulance: string; print: string };
  /** Papers from the photos (E18-01's web substitute): the grid, the sending, what was found. */
  papers: {
    open: string;
    chooseMany: string;
    title: string;
    lead: string;
    lead2: string;
    pick: string;
    gridLead: string;
    picture: string;
    tileIn: string;
    tileOut: string;
    sendOne: string;
    send: string;
    sending: string;
    found: string;
    read: string;
    check: string;
    notHealth: string;
    notSent: string;
    sendRest: string;
    nothingKept: string;
    backToday: string;
  };
  /** The one player (E15-07): its button, its three speeds and the name of their group. */
  player: {
    play: string;
    pause: string;
    speed: string;
    slower: string;
    usual: string;
    faster: string;
    nextPart: string;
    hearStory: string;
  };
  /** The patient's day (W7): the not-feeling-well button, the symptom log, the nudge's two
   *  buttons, the brief, the questions and the post-visit card's yes. Every card's own lines
   *  are the backend's; `fallback` is the backend's offline card, word for word, for a phone
   *  that kept no copy of it (app/channels/safety_strings.py). */
  day: {
    topThree: string;
    notWell: string;
    notWellTitle: string;
    notWellTitleOther: string;
    notWellLead: string;
    wordsLabel: string;
    wordsLabelOther: string;
    send: string;
    sayIt: string;
    stopAndSend: string;
    sending: string;
    whatToDo: string;
    backToday: string;
    symptomsOpen: string; notWellOther: string; symptomsOpenOther: string;
    symptomsTitleSelf: string;
    symptomsTitleOther: string;
    symptomsLead: string;
    symptomsLeadOther: string;
    symptomsKeep: string;
    sendAgain: string;
    symptomsSaved: string;
    nudgeOk: string;
    nudgeWentWell: string;
    nudgeNotToday: string;
    briefOpen: string;
    briefOpenOther: string;
    briefTitle: string;
    questionsOpen: string;
    questionsOpenOther: string;
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
  /** The Record (W5): the Record screens' own lines — titles, buttons, the few sentences
   *  a screen says itself. Every card's words are the backend's. */
  record: {
    title: string;
    titleOther: string;
    medicines: string; medicinesOther: string;
    papers: string; papersOther: string;
    routine: string; routineOther: string;
    timeline: string; timelineOther: string;
    trends: string; trendsOther: string;
    providers: string; providersOther: string;
    changes: string;
    back: string; backOther: string;
    sureYes: string;
    sureYesOther: string;
    sureRead: string;
    disputed: string;
    matchByNameOnly: string[];
    twice: string; twiceOther: string;
    aboutIt: string;
    add: string;
    storyPurpose: string;
    storyHow: string;
    storyWatch: string;
    storyAvoid: string;
    storyForgot: string;
    storyAsk: string;
    storyAskOther: string;
    hearParts: Record<"purpose" | "how_to_take" | "watch_out" | "avoid" | "if_forgotten" | "doctor_question", string>;
    addLead: string;
    addLead2: string;
    nameLabel: string;
    strengthLabel: string;
    howLabel: string;
    howHint: string;
    countLabel: string;
    doctorLabel: string;
    checkIt: string;
    outcomeNew: string; outcomeNewOther: string;
    outcomeRefill: string; outcomeRefillOther: string;
    outcomeChange: string;
    flaggedTitle: string;
    flaggedNone: string; flaggedNoneOther: string;
    severity: Record<"major" | "moderate" | "minor", string>;
    pair: string;
    addIt: string;
    added: string; addedOther: string;
    moreTitle: string;
    moreLead: string;
    moreLabel: string;
    moreYes: string;
    morePhoto: string;
    morePhotoWhy: string;
    morePhotoKept: string;
    orderYes: string;
    orderNo: string;
    papersNone: string;
    papersNoneOther: string;
    paperFrom: string;
    paperOpen: string;
    older: string;
    papersWith: string;
    paperWith: string;
    nothingWith: string;
    factsWith: string;
    factWith: string;
    since: string;
    ended: string;
    seeIllness: string;
    seeDoctor: string;
    endOfList: string;
    status: Record<"planned" | "confirmed" | "attended" | "not_attended" | "cancelled", string>;
    illnessPapers: string;
    illnessVisits: string;
    illnessMoments: string;
    moments: Record<"reading" | "dose_taken" | "symptom" | "discharge" | "visit" | "other", string>;
    photoOn: string;
    letterOn: string;
    paperOn: string;
    putWith: string;
    putThis: string;
    putAsk: string;
    putYes: string;
    putDone: string;
    nothingToPut: string;
    kind: Record<"doctor" | "clinic" | "hospital" | "pharmacy" | "lab" | "other", string>;
    visitsMany: string;
    visitsOne: string;
    lastVisit: string;
    nextVisit: string;
    where: string;
    phone: string;
    medicinesFrom: string;
    notesTitle: string;
    notesOnly: string;
    noteLabel: string;
    noteSave: string;
    noteSaved: string; noteSavedOther: string;
    writtenOn: string;
    waiting: string;
    trendsLead: string;
    analytes: Record<"total_cholesterol" | "ldl" | "hdl" | "triglycerides" | "hba1c" | "creatinine" | "egfr" | "potassium" | "haemoglobin" | "tsh", string>;
    analytesOther: Record<"total_cholesterol" | "ldl" | "hdl" | "triglycerides" | "hba1c" | "creatinine" | "egfr" | "potassium" | "haemoglobin" | "tsh", string>;
    resultOn: string;
    resultOnUnit: string;
    rangeUnder: string;
    rangeOver: string;
    rangeBetween: string;
    noRange: string;
    labRange: string;
    guideRange: string;
    noRangeBecause: Record<"needs_age" | "needs_sex" | "none_on_file", string>;
    anchors: Record<"wake" | "breakfast" | "lunch" | "dinner" | "bed", string>;
    anchorsOther: Record<"wake" | "breakfast" | "lunch" | "dinner" | "bed", string>;
    readings: Record<"blood_pressure" | "blood_sugar" | "weight", string>;
    walk: string;
    notSet: string;
    notSetOther: string;
    setDay: string;
    setDayOther: string;
    timeLabel: string;
    morningCard: string;
    walkAfter: string;
    checkDay: string;
    dayAsk: string;
    dayAskOther: string;
    dayYes: string;
    daySaved: string;
    tableMoment: string;
    tableTime: string;
    tableMedicines: string;
    tableReadings: string;
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
    closeAccount: string;
    closeAccountOther: string;
    closeAccountYes: string;
    closeAccountYesOther: string;
    keepCopy: string;
    savePage: string;
    thread: string;
    threadEarlier: string;
    messageLabel: string;
    sendMessage: string;
    sendingMessage: string;
    keys: string;
    newKey: string;
    holderName: string;
    holderPhone: string;
    roleLabel: string;
    partsLabel: string;
    windowLabel: string;
    makeKey: string;
    seeWords: string;
    wordsLead: string;
    agreeKey: string;
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
    templates: Record<"pickup" | "call_you" | "see_doctor" | "thinking_of_you" | "weigh_tomorrow" | "drink_water", string>;
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
    /** The same six kinds, said about him by name (D1, the shape of `*_THEIRS` in
     *  `backend/app/delivery/strings.py`): `kinds` reads as her own message or her own moment
     *  when it stands alone ("Thinking of you" as a template she is about to send); in a table
     *  of counts it has no one to be about but whoever is named in it, so the metrics screen
     *  (`screens/family/Metrics.tsx`) uses these instead. */
    kindsTheirs: Record<"anticipation" | "check_in" | "pattern" | "commitment" | "recognition" | "presence", string>;
    calendar: string;
    chooseFile: string;
    agree: string;
    bookYes: string;
    notThis: string;
    ladderYes: string;
    deliveries: string;
    settings: string;
    triggers: Record<"morning" | "dose" | "reorder" | "doses_untapped" | "flag" | "visit_tomorrow" | "papers" | "family_message" | "first_week_prompt" | "nudge" | "check_in" | "family_notice", string>;
    channels: Record<"app_push" | "whatsapp" | "caregiver" | "in_app", string>;
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
    /** The red-flag row: no setting chooses how it goes (#162). */
    everyWay: string;
    documents: string;
    tags: Record<"lpa" | "medical_letter" | "consent_form", string>;
    backs: Record<"consent" | "stewardship", string>;
    stillOn: string;
    stoppedChip: string;
    addDocument: string;
    chooseDocument: string;
    whatPaper: string;
  };
  /** The Connect tab's own overview (docs/design/nura-concept-board.html, the Connect screen):
   *  his family, his next call, what is near him, and the family thread — one glance, then the
   *  existing screens each row opens. `familyTitle`, `noFamily`, `noCall`, `nearYouTitle` and
   *  `noNearYou` each have an "…Other" twin, said about him by name on a caregiver's key
   *  (`ABOUT_HIM` in `strings/index.ts`). */
  connect: {
    familyTitle: string; familyTitleOther: string;
    addPerson: string;
    addPersonLine: string;
    noFamily: string; noFamilyOther: string;
    nextCallTitle: string;
    call: string;
    change: string;
    noCall: string; noCallOther: string;
    nearYouTitle: string; nearYouTitleOther: string;
    noNearYou: string; noNearYouOther: string;
    messagesTitle: string;
    noMessages: string;
    seeAllFamily: string;
    seeAllNearYou: string;
    seeAllMessages: string;
    callsTitle: string;
    scheduleCall: string;
    cancelCallButton: string;
    cancelledCall: string;
    personLabel: string;
    whenLabel: string;
    linkLabel: string;
    callLabelLabel: string;
  };
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
  /** The chief's panels on Home (docs/health-feed-spec.md §1): "Sent to Pa this week" and
   *  "Watching for Pa". Each watch and each card is the backend's line; these name the panels,
   *  how often a watch runs, and what she can do. */
  chief: {
    sentTitle: string;
    sentNone: string;
    watchingTitle: string;
    watchingNone: string;
    sourcesNote: string;
    onChange: string;
    daily: string;
    weekly: string;
    beforeVisits: string;
    once: string;
    paused: string;
    pause: string;
    resume: string;
    pauseWatch: string;
    add: string;
    addLead: string;
    added: string;
    dengue: string;
    haze: string;
    heat: string;
    festiveFood: string;
  };
  refusals: Record<string, string | readonly string[]> & { default: string };
}
