import type { Strings } from "./types";

/** English. Every line a patient reads or hears; see `types.ts` for the tag contract. */
export const en = {
  // @patient headline
  appName: "Nura",
  tabs: {
    // @patient headline
    today: "Today",
    // @patient headline
    me: "Me",
  },
  signIn: {
    // @patient headline
    title: "Sign in",
    // @patient
    phoneLead: "Type your phone number.",
    // @patient
    phoneHint: "Start with your country code.",
    // @patient
    nameLead: "What should Nura call you?",
    // @patient phrase
    phoneLabel: "Your phone number",
    // @patient phrase
    nameLabel: "Your name",
    // @patient phrase
    sendCode: "Send me a code",
    // @patient phrase
    useEmail: "Sign in with an email instead",
    // @patient phrase
    usePhone: "Sign in with a phone number instead",
    // @patient
    codeLead: "Nura sent a code to your phone.",
    // @patient
    codeHint: "Type the 6 digits from the message.",
    // @patient
    codeWorks: "The code works for 10 minutes.",
    // @patient phrase
    codeLabel: "The code",
    // @patient phrase
    signInButton: "Sign in",
    // @patient
    emailLead: "Type your email address.",
    // @patient phrase
    emailLabel: "Your email",
    // @patient phrase
    sendLink: "Send me a link",
    // @patient
    linkLead: "Nura sent a link to your email.",
    // @patient
    linkHint: "Type the code from the email here.",
    // @patient phrase
    linkLabel: "The code from the email",
    // @patient
    never: "Nura will never call you to ask for it.",
    // @patient phrase
    back: "Go back",
  },
  doors: {
    // @patient headline
    title: "Who is this for?",
    // @patient phrase
    forMe: "This is for me",
    // @patient
    forMeLine: "Nura will keep your own papers.",
    // @patient phrase
    forSomeone: "This is for someone else",
    // @patient
    forSomeoneLine: "You will look after their papers for them.",
    // @patient phrase
    invited: "Someone let me in",
    // @patient
    invitedLine: "{name} shared their papers with you.",
    // @patient phrase
    waiting: "Papers are waiting for you",
    // @patient
    waitingLine: "{name} made this for you.",
  },
  consent: {
    // @patient headline
    title: "Before we start",
    // @patient
    lead: "Please read these words.",
    // @patient phrase
    agree: "I agree",
    // @patient phrase
    language: "Your language",
  },
  claim: {
    // @patient headline
    title: "These papers are yours",
    // @patient
    setUpBy: "{name}, {relationship}, made this for you.",
    // @patient
    keepsSeeing: "{name} will keep seeing these parts of your papers:",
    // @patient phrase
    mine: "Yes, this is mine",
  },
  forSomeone: {
    // @patient headline
    title: "Who are you setting this up for?",
    // @patient
    lead: "Type their name and phone number.",
    // @patient phrase
    theirName: "Their name",
    // @patient phrase
    theirPhone: "Their phone number",
    // @patient phrase
    relationshipLabel: "Who they are to you",
    // @patient
    asked: "They asked you to do this.",
    // @patient phrase
    create: "Set it up",
  },
  switcher: {
    // @patient headline
    title: "Whose papers?",
    // @patient phrase
    own: "Your own papers",
    // @patient
    roleOwner: "These are your own papers.",
    // @patient
    roleChief: "You look after these papers.",
    // @patient
    roleCaregiver: "You can see some of these papers.",
    // @patient
    roleSteward: "You made these papers for them.",
    // @patient
    roleOther: "You can see these papers.",
  },
  today: {
    // @patient headline
    now: "Now",
    // @patient headline
    forYou: "For you today",
    // @patient headline
    greetingMorning: "Good morning, {name}.",
    // @patient headline
    greetingAfternoon: "Good afternoon, {name}.",
    // @patient headline
    greetingEvening: "Good evening, {name}.",
    // @patient phrase
    taken: "Taken",
    // @patient
    tookMorning: "You took it this morning.",
    // @patient
    tookAfternoon: "You took it this afternoon.",
    // @patient
    tookEvening: "You took it this evening.",
    // @patient
    tookNight: "You took it tonight.",
    // @patient
    allTaken: "You have taken every tablet for today.",
    // @patient
    allTakenSub: "There is nothing more to take today.",
    // @patient
    nothingNow: "There is nothing to take right now.",
    // @patient
    noMedicines: "Nura has no medicines for you yet.",
    // @patient
    noMedicinesSub: "Your family can add them from a pill label.",
    // @patient phrase
    hear: "Hear",
    // @patient headline
    readingTitle: "Your blood pressure",
    // @patient
    readingLead: "Write down this morning's number.",
    // @patient
    readingLeadEvening: "Write down tonight's number.",
    // @patient phrase
    aTablet: "Your tablet",
    // @patient headline
    earlierTitle: "From earlier today",
    // @patient phrase
    readingButton: "Write it down",
    // @patient
    stateStable: "Your day is steady.",
    // @patient
    stateWatch: "Nura is keeping an eye on one thing for you.",
    // @patient
    stateWatchSub: "It is not a worry today.",
    // @patient
    stateAct: "There is one thing to do today.",
    // @patient
    stateActSub: "It is the first card on this page.",
    // @patient
    staleState: "This is from earlier today.",
    // @patient action
    callChief: "Call {name} now.",
    // @patient action
    callFamily: "Call your family now.",
    // @patient
    proud: "You have taken your tablets on {count} days.",
    // @patient
    proudOne: "You have taken your tablets on 1 day.",
    // @patient
    proudNone: "When you tap Taken, this number becomes 1.",
    // @patient
    proudSub: "This number only goes up.",
    // @patient headline
    supplyTitle: "Your tablets",
    // @patient headline
    todayList: "Your tablets for today",
    // @patient
    offline: "Nura cannot reach the internet right now.",
    // @patient
    offlineSub: "This is your Today page from earlier.",
    // @patient
    asOf: "Nura last read your papers on {date} at {time}.",
    // @patient
    cannotReach: "Nura cannot reach your papers right now.",
    // @patient headline
    emergencyTitle: "Emergency card",
    // @patient
    emergencySoon: "Nura will keep your emergency card here.",
    // @patient
    homeScreen1: "You can add Nura to your home screen.",
    // @patient
    homeScreen2: "Tap the Share button at the bottom.",
    // @patient
    homeScreen3: "Then tap Add to Home Screen.",
    // @patient
    fromToday: "This comes from your Today page.",
    // @patient
    fromState: "Nura worked this out on {date}.",
    // @patient
    fromDays: "Nura counted the days you took your tablets.",
  },
  reading: {
    // @patient headline
    title: "Your blood pressure",
    // @patient
    lead: "Type the 2 numbers from the machine.",
    // @patient phrase
    top: "The top number",
    // @patient phrase
    bottom: "The bottom number",
    // @patient phrase
    save: "Save",
    // @patient
    saved: "Nura wrote it down.",
    // @patient phrase
    cancel: "Not now",
  },
  me: {
    // @patient headline
    title: "Me",
    // @patient
    signedInAs: "You are signed in as {name}.",
    // @patient phrase
    language: "Your language",
    // @patient phrase
    en: "English",
    // @patient phrase
    ms: "Bahasa Melayu",
    // @patient phrase
    zh: "中文",
    // @patient phrase
    look: "How Nura looks",
    // @patient phrase
    patient: "Big and simple",
    // @patient phrase
    caregiver: "Smaller, with more on the page",
    // @patient phrase
    lookAuto: "Let Nura choose",
    // @patient phrase
    switchProfile: "Look at someone else's papers",
    // @patient phrase
    signOut: "Sign out",
  },
  errors: {
    // @patient
    network: "Nura cannot reach the internet right now.",
    // @patient phrase
    tryAgain: "Try again",
  },
  // One plain sentence for each way the backend says no, by the refusal's class name
  // (`backend/app/channels/api/refusals.py`). The name itself is never shown.
  // @patient
  refusals: {
    default: "Nura could not do that right now.",
    NoSession: "Please sign in again.",
    NoOpenChallenge: "Ask for a new code first.",
    WrongCode: "That code is not right.",
    ChallengeExpired: "That code is too old now.",
    ChallengeLocked: "Ask for a new code and start again.",
    NoKey: "You cannot see these papers any more.",
    OutOfScope: "This part of the papers is not open to you.",
    OutOfRegion: "These papers are kept in another country.",
    NotTheirsToRead: "Only the owner can see this.",
    NotTheirKeyToCut: "Only the owner can share these papers.",
    NoSuchHolder: "Nura does not know that person.",
    NoConsent: "The owner has not agreed to this.",
    ConsentWithheld: "The owner has not agreed to this yet.",
    NotTheirConsentToGive: "Only the owner can agree to this.",
    NotTheirConsentToWithdraw: "Only the owner can stop this.",
    NotTheClaimant: "These papers were made for someone else.",
    NotTheirsToChange: "You can see the medicines but not change them.",
    NoConsentToWithdraw: "There is nothing to stop.",
    NoKeyToClose: "That sharing is already stopped.",
    NoStewardshipHere: "These papers were not set up for anyone else.",
    NoState: "Nura has nothing to show you here yet.",
    NoSuchReviewCard: "That card is not here any more.",
    NoSuchLine: "That medicine is not on your list.",
    PhotoTooLarge: "That photo is too big for Nura.",
    ProfileAlreadyOwned: "You already have your own papers.",
    AlreadyConfirmed: "You already said yes to this.",
    AlreadyRecorded: "Nura already has this.",
    AlreadyRegistered: "This number is already signed up.",
    AlreadySetUp: "Papers for this number are already set up.",
    WaitingToBeClaimed: "Papers are waiting for you to say yes.",
    NotTheCurrentWording: "The words have changed since you read them.",
    WordingNotOnFile: "Nura does not have those words.",
    NotWhatWasConfirmed: "That is not what you said yes to.",
    NotAConfirmerHere: "Only you can say yes to this.",
    HighRiskNeedsLabelPhoto: "Please take a photo of the label first.",
    NoProvenance: "Nura needs to know where this came from.",
    NoWordsInThatLanguage: "Nura does not have these words in that language yet.",
    NotAPhoto: "Nura can only read a photo here.",
    NothingBehindTheBasis: "Nura needs to know why you look after them.",
    NotAgreedPerPerson: "The owner has not agreed to let this person in.",
    NotForYourself: "Use the other door to keep your own papers.",
    ConfirmationExpired: ["That yes is too old now.", "Please say yes again."],
    AlreadySpent: "You already said yes to this.",
  },
} satisfies Strings;
