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
  shell: { askNura: string; askAbout: string; voice: string; voiceSaid1: string; voiceSaid2: string; close: string; bell: string; back: string; bellFeed: string; bellInsights: string };
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
    /** Demo/dev only (`GET /deployment`): sign in at once as the seeded Pa or Mei
     *  (`app.demo_seed`), no phone number or code typed. */
    tryAsPa: string;
    tryAsMei: string;
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
  home: {
    mostLikely: string; whatChanged: string; nextVisit: string; atTime: string; buyMore: string; missing: string; missingSub: string; missingSubDay: string; bpLabel: string; fromName: string; showAll: string; showFewer: string; bpLast: string;
    /** The new Home hero (P1, the living orb): the "Today" kicker over a busy day's headline,
     *  the insight card's own title, and its button to the item it is about. */
    todayKicker: string;
    insightTitle: string;
    insightTitleOther: string;
    insightOpen: string;
    /** The question under a quiet day's large orb, and the caregiver's twin of it. */
    quietPrompt: string;
    quietPromptOther: string;
    /** A quiet day's four suggestion chips: each goes somewhere real (see Home.tsx). */
    chipReport: string;
    chipMedicines: string;
    chipMedicinesOther: string;
    chipVisit: string;
    chipVisitOther: string;
    chipWeek: string;
    chipWeekOther: string;
    /** Home's own ask bar, docked above the tab bar with the small orb beside it — its own
     *  wording, kept apart from `shell.askNura` ("Ask Nura a question"), which every other
     *  screen's ask bar still uses. */
    askNura: string;
    /** The busy day's one headline, a whole sentence per `HomeTopItem` kind (`today/model.ts`'s
     *  `homeHeadlineFor`), filled only from that kind's own real facts. */
    headlineDoseDue: string;
    headlineDoseDueOther: string;
    headlineAllTaken: string;
    headlineAllTakenOther: string;
    headlineReading: string;
    headlineReadingOther: string;
    headlineVisit: string;
    headlineVisitOther: string;
    headlineVisitNoDoctor: string;
    headlineVisitNoDoctorOther: string;
    headlineReorder: string;
    headlineReorderOther: string;
    /** A newly confirmed paper (owner review round 3, fix #2): filled only from the paper's own
     *  real fields — `{kind}` its plain-word document kind, `{date}` the date printed on it,
     *  `{n}`/`{m}` a real count of numbers outside/on the paper. Never a bare title. */
    headlinePaperOutside: string;
    headlinePaperOutsideOther: string;
    headlinePaperAllIn: string;
    headlinePaperAllInOther: string;
    headlinePaperNoRange: string;
    headlinePaperNoRangeOther: string;
    /** The insight card's own extra fact (owner review round 2): a real thing the headline did
     *  not already say, per `HomeTopItem` kind — never the headline's own sentence again. Where
     *  there is no such fact yet (`today/model.ts`'s `insightExtra`), the card itself does not
     *  render; the rows it would have carried sit directly under the headline instead. */
    tookCount: string;
    tookCountOther: string;
    trendHigher: string;
    trendHigherOther: string;
    trendLower: string;
    trendLowerOther: string;
    trendSame: string;
    trendSameOther: string;
  };
  /** Home's "Things to do" tile (docs/design/nura-concept-board.html): his day's activity —
   *  today's steps, water and meals, each a real write through PR #235's lifestyle logs
   *  (`/metrics/{kind}`, `/food`), with the same week ring the Health tab shows. */
  activity: {
    title: string;
    weekTitle: string;
    stepsLabel: string;
    stepsSave: string;
    waterLabel: string;
    waterSave: string;
    waterSkip: string;
    saved: string;
    mealsTitle: string;
    mealsTitleOther: string;
    meal: { breakfast: string; lunch: string; dinner: string; snack: string };
    skipMeal: string;
    skipped: string;
    skippedOther: string;
  };
  /** The tabs' own titles (D1). */
  places: {
    visitsOwn: string; visitsOwnOther: string;
    visitsOther: string;
    visitsNoneOther: string;
    planTitle: string;
    planLead: string;
    careTitle: string;
    careNoneOwn: string; careNoneOther: string;
    nearYouOwn: string; nearYouOther: string;
    nearYouArea: string; nearYouAreaOther: string;
    guidesTitle: string;
  };
  /** Services' "Help at home" grid (docs/design/nura-concept-board.html, Services' four
   *  tiles): four categories over the same provider directory `places.careTitle` already
   *  reads, told apart by `Provider.category` — never a second, invented directory. */
  homeCare: {
    title: string;
    nursing: string; nursingLine: string;
    physio: string; physioLine: string;
    meals: string; mealsLine: string;
    transport: string; transportLine: string;
    near: string; nearOther: string;
    none: string; noneOther: string;
  };
  /** Care navigation with drafted messages (T3): "Draft a message" on a provider row or a
   *  letter's follow-up line, and the sheet it opens. Nura only ever drafts; the send links
   *  and "Copy" say plainly that he or his chief sends it themselves. */
  navigation: {
    draftAction: string;
    sheetTitle: string;
    copy: string;
    copied: string;
    sendBySms: string;
    sendByWhatsApp: string;
    copyOnly: string;
    loading: string;
    error: string;
  };
  /** The Health tab (docs/design/nura-concept-board.html): "This week", his readings, his day
   *  and Coming up. Every figure and status word beside these is the backend's own
   *  (`health_tab.py`); these are only the screen's own headings and the few lines the backend
   *  does not already say. */
  health: {
    title: string;
    titleOther: string;
    thisWeek: string;
    readingsTitle: string;
    readingsWithheld: string;
    readingsNone: string;
    bloodPressure: string;
    bloodSugar: string;
    readingSource: string;
    readingSourceOther: string;
    metricSource: string;
    metricSourceOther: string;
    asOf: string;
    dayTitle: string;
    dayTitleOther: string;
    mealNotHad: string;
    mealNotHadOther: string;
    comingUpTitle: string;
    addReading: string;
    /** "Your papers" (library part B #2): the short list under Health, and the withheld
     *  line for a key without the records scope — named, never left off the screen blank. */
    papersTitle: string;
    papersWithheld: string;
    // --- package 10: the week ring's calm empty state (a fresh profile, no medicines yet) ---
    ringEmpty: string;
    ringEmptyOther: string;
    // --- package 10 review: one quiet line for every metric with nothing written down, never
    //     a separate empty row each ---
    metricsNotLogged: string;
    metricsNotLoggedOther: string;
  };
  /** The weekly report (W1, docs/design/nura-concept-board.html): the Health card, the live
   *  trace while it builds, the report itself, and the bell's row that opens it. */
  insights: {
    cardTitle: string;
    cardTitleOther: string;
    cardNone: string;
    cardNoneOther: string;
    cardLastLooked: string;
    generate: string;
    screenTitle: string;
    screenTitleOther: string;
    working: string;
    weekOf: string;
    sectionTitles: Record<"what_changed" | "worth_a_look" | "medicines_and_supplements" | "what_you_pay" | "screenings_due" | "questions_for_the_doctor", string>;
    sectionWithheld: string;
    sectionEmpty: string;
    why: string;
    sure: string;
    likely: string;
    worthALook: string;
    askThis: string;
    asked: string;
    noVisit: string;
    // --- package 10: the Health Analyst screen, in the blueprint's language --------------
    /** "Look again": the same `generate()` call as `generate` ("Generate now"), offered once
     *  a report is already on screen rather than before the first one ever exists. */
    lookAgain: string;
    /** The quiet list of every earlier report, opened one at a time. */
    pastTitle: string;
    /** A connection that dropped mid-stream, or the stream's own refusal: what already
     *  arrived stays on screen (`Notice` already says the refusal's own sentence); this is
     *  the way to try again. */
    retryAfterError: string;
    /** Who "Ask … this" names when `ask_who` is `"doctor"` and no visit names one — the same
     *  fallback word the backend's own `doctor_to_ask`/`YOUR_DOCTOR` already picks. A real
     *  name (the next visit's own doctor) is used instead when the record has one. */
    yourDoctor: string;
    yourDoctorOther: string;
    /** The same fallback for `ask_who === "pharmacist"` — there is no "named pharmacist" on
     *  the record, so this is always the word used. */
    yourPharmacist: string;
    yourPharmacistOther: string;
  };
  /** Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html` scene
   *  `insight`): the screen right after a paper is confirmed — the headline, what the engine
   *  really read, one card of the questions it raises for the doctor, and where "Keep these
   *  for my visit" filed them. */
  paperInsight: {
    screenTitle: string;
    screenTitleOther: string;
    /** "Looked at" — the quiet chip label ahead of what the stream really read
     *  (`docs/design/experience-blueprint.html`'s own `looked()`), never a person's name. */
    lookedAt: string;
    /** "For {doctor} on {date}" — the card's own title when the next visit names both; no
     *  `…Other` twin (a doctor's name and a date name nobody). */
    forDoctorOn: string;
    forNextVisit: string;
    forNextVisitOther: string;
    /** "Questions to ask, never answers." — the first half of the safety note; the second is
     *  the report table's own `onboarding.records.safetyNotAdvice`, said once, not composed
     *  twice for the same idea (`make language`'s own phrase-consistency gate). */
    questionsNotAnswers: string;
    keepForVisit: string;
    keepForVisitOther: string;
    keeping: string;
    kept: string;
    keptForVisit: string;
    keptForVisitOther: string;
    /** With no upcoming visit, Nura keeps nothing (#303 review, B3, the honest fallback) —
     *  said plainly, in place of a false "kept" claim. Two lines, one idea each, the same
     *  `plain-words` rule 2 discipline `keptUnfiled` used to hold to. */
    keepNoVisit: readonly string[];
    keepNoVisitOther: readonly string[];
    notNow: string;
  };
  signIn: {
    title: string;
    phoneLead: string;
    phoneHint: string;
    nameLead: string;
    phoneLabel: string;
    nameLabel: string;
    sendCode: string;
    sending: string;
    sent: string;
    useEmail: string;
    usePhone: string;
    codeLead: string;
    codeHint: string;
    codeWorks: string;
    codeLabel: string;
    signInButton: string;
    checking: string;
    signedIn: string;
    resend: string;
    resendDone: string;
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
    greeting: string;
    forMe: string;
    forMeLine: string;
    forSomeone: string;
    forSomeoneLine: string;
    invited: string;
    invitedLine: string;
    waiting: string;
    waitingLine: string;
    lookAgain: string;
    meIntro: string;
    meName: string;
    met: string;
    privacyKeeps: string;
    privacyChoose: string;
    continueWord: string;
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
    didYouKnow: string;
    ask: string;
    family: string;
    notForMe: string;
    keepGoing: string;
    toTablets: string;
    declined: string;
    declinedToday: string;
    shared: string;
    fromPublisher: string;
    whyLink: string;
    whyTitle: string;
    cannotShare: string;
    quiet: string;
    quietSub: string;
    nothingMore: string;
    offlineSub: string;
    askTitle: string;
    askAbout: string;
    askLabel: string;
    askLead: string;
    askSample1: string;
    askSample1Theirs: string;
    askSample2: string;
    askSample2Theirs: string;
    askSample3: string;
    askSample3Theirs: string;
    sourcePapers: string;
    sourceMedicines: string;
    sourceVisits: string;
    sourceReviewCard: string;
    askWithheld: string;
    askThinking: string;
    lookingForToday: string;
    askAnswered: string;
    askLookedAt: string;
    newConversation: string;
    earlierInConversation: string;
    back: string;
    statusHeld: string;
    statusSent: string;
    statusOpened: string;
    statusPlayed: string;
    statusDismissed: string;
    play: string;
    watchAgain: string;
    watchWhole: string;
    watchWholeShort: string;
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
    insurance: string;
  };
  /** Profile's Insurance row (E13-03): his policies, in plain words — one row each. The Ledger
   *  (claim amounts, #260) is a later screen; this is the policy list alone. */
  insurance: {
    title: string;
    titleOther: string;
    none: string;
    noneOther: string;
    type: Record<"hospital" | "outpatient" | "critical_illness" | "government_scheme", string>;
    status: Record<"active" | "lapsed" | "cancelled", string>;
    covers: string;
    covered: string;
    renews: string;
    premiumDue: string;
    reference: string;
    /** The passport (package 12a): loading a policy paper, the four sections built from what
     *  is really on the record, and the claims filed against it — a clearly separate block so
     *  this package's strings never collide with another builder's edit to the block above. */
    passport: {
      coversTitle: string;
      excludesTitle: string;
      benefitsTitle: string;
      claimTitle: string;
      /** Two short lines, never one two-idea sentence (plain-words rule 2) — the calm line
       *  every section shows when nothing is on file for it. */
      notFound: readonly [string, string];
      noPaperYet: readonly [string, string];
      worksByGuaranteeLetter: string;
      claimedThisYear: string;
      paidByInsurer: string;
      paidByPatient: string;
      claimsTitle: string;
      addPolicy: string;
      loadTitle: string;
      proposeTitle: string;
      proposeSub: string;
      policyTypeLabel: string;
      proposeCta: string;
      proposeCtaBusy: string;
      proposeCtaDone: string;
      notAPolicy: readonly [string, string];
      savedAsPaper: string;
      /** "From {date}" / "to {date}" — the passport card's own period line, built from the
       *  confirmed start/end dates, never a free-text guess. */
      periodFrom: string;
      periodTo: string;
      /** "p. {page}" — the quiet page marker after an essentials line. */
      pageMarker: string;
      /** "Show all {n}" — the disclosure under the first five lines of a longer section. */
      showAllN: string;
      whoToContact: string;
      seePolicyItself: string;
      /** The insurance-specific safety line (item 10): two short lines, replacing the report
       *  table's lab-oriented "ranges are printed" line for an insurance kind only. Written
       *  impersonally (never "your"/"his") so the same line is correct read to him or about
       *  him, the same register `app.insurance.strings`' own lines already keep. */
      confirmSafety: readonly [string, string, string];
      /** "Fix something" — the report table's fix-hint pill, for a card with no numeric
       *  result rows at all (a policy, a letter), in place of "Fix a number". */
      fixSomething: string;
      /** Two short lines, never one two-idea sentence (plain-words rule 2): "Nura read the
       *  first {n} lines of this section." / "There may be more on the policy." — shown under
       *  any essentials section a write actually cut at the backend's own cap
       *  (`PolicyOut.essentials_cut`), and the same two lines again on the confirmation card
       *  when any section would be cut once saved (independent review, package 12a fix round,
       *  item 4) — never inferred from a list's own length. */
      essentialsCutNotice: readonly [string, string];
      /** "Waiting time: {text}" — the passport's own label for the printed waiting-period
       *  line, so it reads as a labelled fact rather than a bare, unexplained sentence
       *  (independent review, operator capture note). */
      waitingPeriodLabel: string;
      /** "As typed" — the small label under a covers/covered line shown from the policy's own
       *  typed word (`Policy.covers`) rather than a paper's essentials list, so the two
       *  sources are never confused for one another (independent review, item 3). */
      typedLabel: string;
    };
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
    working: string;
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
    /** The header's own compact pill (cp3-home, owner review round 2): two words, never the
     *  whole phrase — `notWell(Other)` is still what a screen reader says (the pill's own
     *  `aria-label`). */
    notWellShort: string;
    notWellShortOther: string;
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
    costOpen: string;
    costOpenOther: string;
    costTitle: string;
    costCoveredLabel: string;
    costCoveredLabelOther: string;
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
      headSelf: string;
      headOther: string;
      loading: string;
      lead: string;
      lead2: string;
      lead3: string;
      noted: string;
      removed: string;
      pickedPlainSelf: string;
      pickedPlainOther: string;
      pickedAddedSelf: string;
      pickedAddedOther: string;
      removedSelf: string;
      removedOther: string;
      removedSub: string;
      more: string;
      fewer: string;
      done: string;
      term: string;
      countNone: string;
      count: string;
      ackSelf: string;
      ackOther: string;
      and: string;
      tellMe: string;
      tellMeLead: string;
      tellMeLabel: string;
      tellMeSend: string;
      tellMeNothing: string;
      tellMeNothingSub: string;
      tellMeSafety: string;
      tellMeSafetySub: string;
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
      photoHint: string;
      file: string;
      fileHint: string;
      manyHint: string;
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
      leftOutByYou: string;
      aboutThisPaper: string;
      checkedOn: string;
      checkedOnOther: string;
      seePaperItself: string;
      askAboutPaper: string;
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
      valueUnreadable: string;
      kindHandwritten: string;
      kindInsuranceLetter: string;
      kindInsurancePolicy: string;
      kindInsuranceClaim: string;
      kindDeviceScreen: string;
      kindOther: string;
      kindPillPhoto: string;
      kindPharmacyReceipt: string;
      pillProposal: string;
      unreadable: string;
      typeIt: string;
      fromPage: string;
      readingSomeOutside: string;
      readingAllInRange: string;
      readingLinesRead: string;
      chipOutside: string;
      chipInRange: string;
      chipCheck: string;
      flagAbove: string;
      flagBelow: string;
      flagInRange: string;
      checkThisOne: string;
      seeFullTable: string;
      fixHint: string;
      fixNumber: string;
      nuraRead: string;
      checkSheetTitle: string;
      checkSheetConfirm: string;
      checkSheetConfirming: string;
      checkSheetConfirmed: string;
      safetyRanges: string;
      safetyNotAdvice: string;
      fromPageAndDate: string;
      fromPaperOn: string;
      dateAndFacility: string;
      titleLabReport: string;
      titleMedicineLabel: string;
      titleDischargeLetter: string;
      titleClinicSlip: string;
      titleHandwritten: string;
      titleInsuranceLetter: string;
      titleInsurancePolicy: string;
      titleInsuranceClaim: string;
      titleDeviceScreen: string;
      titleOtherKind: string;
      titlePillPhoto: string;
      titlePharmacyReceipt: string;
      titleUnknown: string;
      whoseLeadBoth: string;
      whoseLeadNameOnly: string;
      whoseLeadYearOnly: string;
      whoseLeadGeneric: string;
      whoseLeadGenericOther: string;
      whoseQuestion: string;
      whoseQuestionOther: string;
      whoseMine: string;
      whoseMineOther: string;
      whoseSomeoneElses: string;
      whoseNotSure: string;
      whoseSetAside: string;
      whoseSetAsideOther: string;
      duplicateLead: string;
      duplicateQuestion: string;
      duplicateSame: string;
      duplicateDifferent: string;
      duplicateSetAside: string;
      duplicateAddedOn: string;
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
    add: string; addOther: string;
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
    // --- redesign package 11: "Your tablets" (the registry) and Add a medicine -----------
    /** The form field of the short typed form ("tablet", "capsule", "inhaler…") — the one
     *  field a photo never fills (the extractor names no "form" attribute), typed-only. */
    formLabel: string;
    /** "Type it in.": the third way into Add a medicine, beside a photo and a file. */
    addTypeIt: string;
    /** The typed form's own lead line — never "check what Nura read" when nothing was. */
    addTypeLead: string;
    /** The confirmation card's two actions once a photo or a file has been read. */
    addLooksRight: string;
    addFix: string;
    /** The which-one question (#302): "STATIN" is a family, not one medicine. */
    addWhichLead: string;
    addWhichQuestion: string;
    addWhichHint: string;
    /** The chip beside the register's own choices, when he does not know which one it is. */
    addNotSure: string;
    addNotSureNote: string[];
    /** The confirm card's own turn when the source was a photo of a loose tablet (#2b,
     *  independent safety review): never the ordinary "read from the label" turn, and never
     *  a one-tap "Looks right" beside it — a pill photo is a guess, not a read. */
    addPillConfirmTurn: string;
    /** "This might be {name}." plus why Nura cannot be sure and what to do about it — shown
     *  before he ever sees a one-tap accept, because for a pill photo there is none. */
    addPillCaution: string[];
    /** The pill photo's own way forward: the field-by-field form, never a single tap. */
    addPillCheckEach: string;
    /** After his yes: where it went, and the way back to see it (a `ConnectionRow`). */
    addedConnection: string; addedConnectionOther: string;
    seeInRegistry: string; seeInRegistryOther: string;
    /** A label that adds nothing new (`Outcome.DUPLICATE`): the existing engine's own
     *  answer, put as a question rather than left as a bare refusal. */
    addDuplicateQuestion: string[]; addDuplicateQuestionOther: string[];
    addDuplicateYes: string;
    addDuplicateNo: string;
    /** The same photo or entry already wrote this medicine once (`matched_line_id` null on
     *  a `DUPLICATE` outcome, #11): nothing to ask a quantity for, so no "yes" — only the
     *  way back. */
    addAlreadySaved: string[]; addAlreadySavedOther: string[];
    /** The registry's own "Today" section, above the list (redesign package 11). */
    todayKick: string;
    /** "12 left" — a registry row's own small chip, only when the count knows a number. */
    leftChip: string;
    /** The Add screen's back link into the registry it actually goes back to — never the
     *  generic "Back to your papers" every other Record screen's frame says. */
    backToMedicines: string; backToMedicinesOther: string;
    /** The turn framing's own lines (redesign package 11, the owner's rejection of the old
     *  Record frame): a headline and a hint for each step, said as Nura, never a bare title. */
    addEntryTurn: string;
    addConfirmTurn: string;
    addConfirmHint: string;
    /** The boundary on the add flow (never the lab-ranges line): the same rule the
     *  medicine's own story already carries, said once here before his yes. */
    addBoundary: string[];
    /** The medicine detail sheet's own quiet row labels (redesign package 11). */
    sheetForm: string;
    sheetHowMany: string;
    sheetLeft: string;
    sheetFrom: string;
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
    /** "Your papers" full list (library part B #2): the way to it from Health's short list. */
    seeAllPapers: string;
    seeAllPapersOther: string;
    /** A confirmed lab paper's state chip, from `rangeStatus`: how many results sit outside
     *  the paper's own printed range, or that none do. Never a bare count. */
    paperChipOutside: string;
    paperChipInRange: string;
    /** A waiting paper's state chip — the short word, distinct from the sheet's own longer
     *  `onboarding.records.checkThisOne`. */
    paperChipCheck: string;
    /** Any other confirmed kind (a letter, a receipt): read again, never re-checked. */
    paperChipRead: string;
    /** Grouping the full list by year once there are enough papers to need it. */
    paperYearGroup: string;
    /** "Ask about this paper" (library part B #3) opens Ask with the paper named — a draft
     *  he finishes and sends himself, never asked on its own. */
    paperAskPrefill: string;
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
    ledger: string;
    ledgerOther: string;
    ledgerWithheld: string;
    ledgerWithheldOther: string;
    ledgerTotals: string;
    ledgerClaimedLabel: string;
    ledgerInsurerPaidLabel: string;
    ledgerPatientPaidLabel: string;
    ledgerPatientPaidLabelOther: string;
    ledgerNone: string;
    ledgerOn: string;
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
  /** T2's "Nura suggests" rows (Health's Coming up, Connect's next-visit tile): what the
   *  planner found, in the screen's own words — the backend's own line (`purpose`) is shown
   *  to the owner as it is written; a caregiver's key reads `rowOther` by name instead, never
   *  the backend's "you" line. "Book it" opens the visits tab with the proposal ready to
   *  book; "Not now" hides it for 90 days (`app.reasoning.visits.planner`). */
  visitSuggest: {
    followUpWhy: string;
    medicineReviewWhy: string;
    testComingWhy: string;
    screeningDueWhy: string;
    rowOther: string;
    bookIt: string;
    notNow: string;
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
