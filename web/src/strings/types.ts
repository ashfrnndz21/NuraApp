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
    signOut: string;
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
  };
  errors: { network: string; tryAgain: string };
  /** One line per refusal, or two when the second says what to do next; each line one idea. */
  refusals: Record<string, string | readonly string[]> & { default: string };
}
