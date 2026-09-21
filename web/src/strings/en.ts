import type { Strings } from "./types";

/** English. Every line a patient reads or hears; see `types.ts` for the tag contract. */
export const en = {
  // @patient headline
  appName: "Nura",
  demo: {
    // @patient headline
    banner: "Demo — not for real health information",
    // @patient headline
    bannerShort: "Demo. No real health information.",
    // @patient
    lines: ["This is a demo.", "Do not put real health information in it.", "Everything here is wiped each night."],
  },
  tabs: {
    // @patient headline
    today: "Today",
    // @patient headline
    record: "Papers",
    // @patient headline
    me: "Me",
    // @patient headline
    family: "Family",
    // @patient headline
    home: "Home",
    // @patient headline
    medicines: "Medicines",
    // @patient headline
    records: "Papers",
    // @patient headline
    visits: "Visits",
    // @patient headline
    timeline: "Papers",
    // @patient headline
    plan: "Plan",
    // @patient headline
    health: "Health",
    // @patient headline
    connect: "Connect",
    // @patient headline
    services: "Services",
    // @patient headline
    profile: "Profile",
  },
  shell: {
    // @patient phrase
    askNura: "Ask Nura a question",
    // @patient phrase
    askAbout: "Ask about {name}",
    // @patient phrase
    voice: "Speak",
    // @patient
    voiceSaid1: "Press the small microphone beside the letters.",
    // @patient
    voiceSaid2: "Then say your question.",
    // @patient phrase
    close: "Close",
    // @patient phrase
    bell: "More for you",
    // @patient phrase
    back: "Go back",
    // @patient phrase
    bellFeed: "More for you",
    // @patient phrase
    bellInsights: "Your week, looked at closely",
  },
  welcome: {
    // @patient headline
    tagline1: "Your health, kept together.",
    // @patient headline
    tagline2: "Your family, close by.",
    // @patient
    lead: "Nura keeps your medicines and your papers in one place.",
    // @patient headline
    remember: "Remember",
    // @patient line
    rememberLine: "Nura remembers your medicines and your papers.",
    // @patient headline
    share: "Share",
    // @patient line
    shareLine: "You choose who in your family can see them.",
    // @patient headline
    prepare: "Prepare",
    // @patient line
    prepareLine: "Nura gets you ready before you see the doctor.",
    // @patient phrase
    start: "Get started",
    // @patient phrase
    tryAsPa: "Try it as Pa",
    // @patient phrase
    tryAsMei: "Try it as Mei",
  },
  talk: {
    // @patient phrase
    you: "You asked",
    // @patient phrase
    nura: "Nura said",
    // @patient
    working: "Nura is looking.",
    // @patient
    answered: "Nura has an answer.",
    // @patient headline
    lookedAt: "What Nura looked at",
    // @patient
    slow: "This is taking longer than usual.",
    // @patient
    failed: "Nura could not answer just now.",
    // @patient phrase
    tryAgain: "Try again",
    // @patient phrase
    loading: "Nura is getting your Today page ready.",
  },
  hub: {
    // @patient
    howFeeling: "How are you today?",
    // @patient
    howFeelingOther: "How is {patient} today?",
    // @patient headline
    checkTitle: "How you feel today",
    // @patient headline
    checkTitleOther: "How {patient} feels today",
    // @patient line
    checkLine: "Tell Nura how you feel today.",
    // @patient phrase
    checkLineOther: "Tell Nura how {patient} feels today",
    // @patient phrase
    checkIn: "Tell Nura",
    // @patient
    doTitle: "What would you like to do?",
    // @patient
    doTitleOther: "What to do for {patient}.",
    // @patient headline
    health: "Health",
    // @patient line
    healthLine: "Your blood pressure book and your papers.",
    // @patient line
    healthLineOther: "{patient}'s blood pressure book and papers.",
    // @patient headline
    medicines: "Medicines",
    // @patient line
    medicinesLine: "Your tablets, and when to take them.",
    // @patient line
    medicinesLineOther: "{patient}'s tablets, and when to take them.",
    // @patient headline
    connect: "Connect",
    // @patient line
    connectLine: "See your family and friends.",
    // @patient line
    connectLineOther: "See {patient}'s family and friends.",
    // @patient headline
    activities: "Things to do",
    // @patient line
    activitiesLine: "Stay busy.",
    // @patient headline
    care: "Care services",
    // @patient line
    careLine: "Help at home.",
    // @patient line
    careLineOther: "Help {patient} at home.",
    // @patient headline
    resources: "Guides",
    // @patient line
    resourcesLine: "Read and learn.",
    // @patient headline
    report: "Add a paper",
    // @patient line
    reportLine: "Take a photo of it, or choose the one your doctor sent you.",
    // @patient line
    reportLineOther: "Take a photo of it, or choose the one {patient}'s doctor sent.",
    // @patient line
    reportNote: "Nura will read it and show you what it found.",
    // @patient line
    reportNoteOther: "Nura will read it and show what it found.",
    // @patient line
    reportReady: "Nura will not send this until you say so.",
    // @patient phrase
    reportReadyOther: "Nura will not send this for {patient} until you say so.",
    // @patient phrase
    reportSend: "Send it",
    // @patient headline
    upcoming: "Next visit",
    // @patient phrase
    seeAll: "See all",
    // @patient phrase
    seeAllVisits: "See all visits",
    // @patient
    soonLine1: "Nura cannot do this yet.",
    // @patient
    soonLine2: "We are still making it.",
    // @patient phrase
    backHome: "Back to your Today page",
    // @patient phrase
    backHomeOther: "Back to {patient}'s Today page",
  },
  home: {
    // @patient headline
    mostLikely: "How things are today",
    // @patient headline
    whatChanged: "What changed",
    // @patient headline
    nextVisit: "Next visit",
    // @patient phrase
    atTime: "At {time}.",
    // @patient headline
    buyMore: "Buy more",
    // @patient headline
    missing: "Not in the papers yet",
    // @patient
    missingSub: "Nura added these to the questions for {doctor} on {date}.",
    // @patient
    missingSubDay: "Nura added these to the questions for the visit on {date}.",
    // @patient phrase
    bpLabel: "Blood pressure, the top number",
    // @patient headline
    fromName: "From {name}",
    // @patient phrase
    showAll: "See all {count}",
    // @patient phrase
    showFewer: "See fewer",
    // @patient
    bpLast: "The last blood pressure had a top number of {number}.",
    // @patient headline
    todayKicker: "Today",
    // @patient headline
    insightTitle: "Your health",
    // @patient headline
    insightTitleOther: "{patient}'s health",
    // @patient phrase
    insightOpen: "See more about this",
    // @patient
    quietPrompt: "What shall we look at?",
    // @patient
    quietPromptOther: "What shall we look at for {patient}?",
    // @patient phrase
    chipReport: "Read a report",
    // @patient phrase
    chipMedicines: "My medicines",
    // @patient phrase
    chipMedicinesOther: "{patient}'s medicines",
    // @patient phrase
    chipVisit: "My next visit",
    // @patient phrase
    chipVisitOther: "{patient}'s next visit",
    // @patient phrase
    chipWeek: "How was my week?",
    // @patient phrase
    chipWeekOther: "How was {patient}'s week?",
    // @patient phrase
    askNura: "Ask Nura anything",
    // @patient headline
    headlineDoseDue: "{title} is due at {when}.",
    // @patient headline
    headlineDoseDueOther: "{patient}'s {title} is due at {when}.",
    // @patient headline
    headlineAllTaken: "Every tablet for today is taken.",
    // @patient headline
    headlineAllTakenOther: "Every tablet for {patient} today is taken.",
    // @patient headline
    headlineReading: "Your blood pressure today was {systolic} over {diastolic}.",
    // @patient headline
    headlineReadingOther: "{patient}'s blood pressure today was {systolic} over {diastolic}.",
    // @patient headline
    headlineVisit: "You see {doctor} on {weekday}.",
    // @patient headline
    headlineVisitOther: "{patient} sees {doctor} on {weekday}.",
    // @patient headline
    headlineVisitNoDoctor: "You have a visit on {weekday}.",
    // @patient headline
    headlineVisitNoDoctorOther: "{patient} has a visit on {weekday}.",
    // @patient headline
    headlineReorder: "About {days} days of {title} are left.",
    // @patient headline
    headlineReorderOther: "About {days} days of {patient}'s {title} are left.",
    // @patient headline
    headlinePaperOutside: "{n} of {m} numbers on your {kind} from {date} are outside range on the paper.",
    // @patient headline
    headlinePaperOutsideOther: "{n} of {m} numbers on {patient}'s {kind} from {date} are outside range on the paper.",
    // @patient headline
    headlinePaperAllIn: "Every number on your {kind} from {date} is inside the range on the paper.",
    // @patient headline
    headlinePaperAllInOther: "Every number on {patient}'s {kind} from {date} is inside the range on the paper.",
    // @patient headline
    headlinePaperNoRange: "Your {kind} from {date} is in your papers.",
    // @patient headline
    headlinePaperNoRangeOther: "{patient}'s {kind} from {date} is in the papers.",
    // @patient headline
    tookCount: "You took {done} of {total} today.",
    // @patient headline
    tookCountOther: "{patient} took {done} of {total} today.",
    // @patient headline
    trendHigher: "That is higher than your blood pressure last time.",
    // @patient headline
    trendHigherOther: "That is higher than {patient}'s blood pressure last time.",
    // @patient headline
    trendLower: "That is lower than your blood pressure last time.",
    // @patient headline
    trendLowerOther: "That is lower than {patient}'s blood pressure last time.",
    // @patient headline
    trendSame: "That is about the same as your blood pressure last time.",
    // @patient headline
    trendSameOther: "That is about the same as {patient}'s blood pressure last time.",
  },
  activity: {
    // @patient headline
    title: "Things to do",
    // @patient headline
    weekTitle: "This week",
    // @patient phrase
    stepsLabel: "Steps today",
    // @patient phrase
    stepsSave: "Save",
    // @patient phrase
    waterLabel: "Cups of water today",
    // @patient phrase
    waterSave: "Save",
    // @patient phrase
    waterSkip: "No water today",
    // @patient
    saved: "Nura wrote it down.",
    // @patient headline
    mealsTitle: "Your meals today",
    // @patient headline
    mealsTitleOther: "{patient}'s meals today",
    // @patient phrase
    meal: { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner", snack: "Snack" },
    // @patient phrase
    skipMeal: "Did not have this",
    // @patient
    skipped: "You did not have this.",
    // @patient
    skippedOther: "{patient} did not have this.",
  },
  places: {
    // @patient headline
    visitsOwn: "Your visits",
    // @patient headline
    visitsOwnOther: "{patient}'s visits",
    // @patient headline
    visitsOther: "{name}'s visits",
    // @patient
    visitsNoneOther: "Nura has no visit written down for {name}.",
    // @patient headline
    planTitle: "Plan for the next visit",
    // @patient
    planLead: "Everything for the next visit is here.",
    // @patient headline
    careTitle: "Care services",
    // @patient
    careNoneOwn: "Nura has no local care service to show you yet.",
    // @patient
    careNoneOther: "Nura has no local care service to show for {name} yet.",
    // @patient headline
    nearYouOwn: "Near you",
    // @patient headline
    nearYouOther: "Near {name}",
    // @patient
    nearYouArea: "Nura knows your area is {area}.",
    // @patient
    nearYouAreaOther: "Nura knows {name}'s area is {area}.",
    // @patient headline
    guidesTitle: "Guides",
  },
  homeCare: {
    // @patient headline
    title: "Help at home",
    // @patient phrase
    nursing: "Nursing at home",
    // @patient phrase
    nursingLine: "A nurse comes to you",
    // @patient phrase
    physio: "Physio",
    // @patient phrase
    physioLine: "Keep moving well",
    // @patient phrase
    meals: "Meals",
    // @patient phrase
    mealsLine: "Delivered to you",
    // @patient phrase
    transport: "Transport",
    // @patient phrase
    transportLine: "To your visits",
    // @patient phrase
    near: "Near you",
    // @patient phrase
    nearOther: "Near {name}",
    // @patient
    none: "Nura has nothing near you for this yet.",
    // @patient
    noneOther: "Nura has nothing near {name} for this yet.",
  },
  navigation: {
    // @patient phrase
    draftAction: "Draft a message",
    // @patient headline
    sheetTitle: "Your drafted message",
    // @patient phrase
    copy: "Copy",
    // @patient
    copied: "It is copied, ready to paste where you send it.",
    // @patient phrase
    sendBySms: "Send by text message",
    // @patient phrase
    sendByWhatsApp: "Send by WhatsApp",
    // @patient
    copyOnly: "There is no number for this place, so copy the message and send it yourself.",
    // @patient
    loading: "Nura is writing the message.",
    // @patient
    error: "Nura could not write the message just now.",
  },
  health: {
    // @patient headline
    title: "Your health",
    // @patient headline
    titleOther: "{name}'s health",
    // @patient headline
    thisWeek: "This week",
    // @patient headline
    readingsTitle: "Blood pressure book and sugar numbers",
    // @patient
    readingsWithheld: "This key does not cover {name}'s blood pressure book.",
    // @patient
    readingsNone: "Nothing written down yet.",
    // @patient phrase
    bloodPressure: "Blood pressure",
    // @patient phrase
    bloodSugar: "Blood sugar",
    // @patient phrase
    readingSource: "From your blood pressure book, {date}",
    // @patient phrase
    readingSourceOther: "From {name}'s blood pressure book, {date}",
    // @patient phrase
    metricSource: "From what you wrote down, {date}",
    // @patient phrase
    metricSourceOther: "From what {name} wrote down, {date}",
    // @patient phrase
    asOf: "As of {date}",
    // @patient headline
    dayTitle: "Your day",
    // @patient headline
    dayTitleOther: "{name}'s day",
    // @patient
    mealNotHad: "You did not have this.",
    // @patient
    mealNotHadOther: "{name} did not have this.",
    // @patient headline
    comingUpTitle: "Coming up",
    // @patient phrase
    addReading: "Write down a blood pressure",
    // @patient headline
    papersTitle: "Your papers",
    // @patient
    papersWithheld: "This key does not cover {name}'s papers.",
  },
  insights: {
    // @patient headline
    cardTitle: "Your week, looked at closely",
    // @patient headline
    cardTitleOther: "{name}'s week, looked at closely",
    // @patient
    cardNone: "Nura has not looked at your week yet.",
    // @patient
    cardNoneOther: "Nura has not looked at {name}'s week yet.",
    // @patient phrase
    cardLastLooked: "Nura looked at this on {date}",
    // @patient phrase
    generate: "Generate now",
    // @patient headline
    screenTitle: "Your week",
    // @patient headline
    screenTitleOther: "{name}'s week",
    // @patient
    working: "Nura is looking at this week.",
    // @patient phrase
    weekOf: "The week of {date}",
    sectionTitles: {
      // @patient headline
      what_changed: "What changed",
      // @patient headline
      worth_a_look: "Worth a look",
      // @patient headline
      medicines_and_supplements: "Medicines and supplements",
      // @patient headline
      what_you_pay: "What you pay",
      // @patient headline
      screenings_due: "Screenings due",
      // @patient headline
      questions_for_the_doctor: "Questions for the doctor",
    },
    // @patient
    sectionWithheld: "This key does not cover this part of {name}'s week.",
    // @patient
    sectionEmpty: "There is nothing here this week.",
    // @patient phrase
    why: "Why",
    // @patient phrase
    sure: "Sure",
    // @patient phrase
    likely: "Likely",
    // @patient phrase
    worthALook: "Worth a look",
    // @patient phrase
    askThis: "Ask {who} this",
    // @patient
    asked: "Nura kept this question for your visit.",
    // @patient
    noVisit: "There is no visit booked yet to take this to.",
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
    // @patient phrase
    lookAgain: "Look again",
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
    relationshipLabel: "Who you are to them",
    // @patient phrase
    relationships: {
      daughter: "Their daughter",
      son: "Their son",
      spouse: "Their husband or wife",
      sibling: "Their brother or sister",
      grandchild: "Their grandchild",
      other_family: "Someone else in their family",
      helper: "Their helper",
      friend: "Their friend",
      neighbour: "Their neighbour",
      other: "Someone else",
    },
    // @patient phrase
    pickContact: "Choose from my contacts",
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
    // @patient phrase
    openOwn: "Your own papers. Tap to look at someone else's papers.",
    // @patient phrase
    openOther: "{name}'s papers. Tap to look at someone else's papers.",
    // @patient
    onlyThese: "These are the only papers Nura has for you.",
    // @patient
    cannotLook: "Nura cannot look for other papers right now.",
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
    // @patient headline
    readingTitleOther: "{patient}'s blood pressure",
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
    stateStableOther: "{patient}'s day is steady.",
    // @patient
    stateWatchOther: "Nura is keeping an eye on one thing for {patient}.",
    // @patient
    callFamilyOther: "Call the rest of the family now.",
    // @patient
    offlineSubOther: "This is {patient}'s Today page from earlier.",
    // @patient
    asOfOther: "Nura last read {patient}'s papers on {date} at {time}.",
    // @patient
    cannotReachOther: "Nura cannot reach {patient}'s papers right now.",
    // @patient
    emergencySoonOther: "Nura will keep {patient}'s emergency card here.",
    // @patient headline
    todayListOther: "{patient}'s tablets for today",
    // @patient
    fromTodayOther: "This comes from {patient}'s Today page.",
    // @patient
    tookMorningOther: "{patient} took it this morning.",
    // @patient
    allTakenOther: "{patient} has taken every tablet for today.",
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
    // @patient phrase
    emergencyOpen: "Your emergency card",
    // @patient phrase
    emergencyOpenOther: "{patient}'s emergency card",
  },
  feed: {
    // @patient headline
    title: "More for you",
    // @patient
    empty: "Nothing new is waiting today.",
    // @patient phrase
    emptyAction: "Back to Today",
    // @patient phrase
    open: "See more for you",
    // @patient headline
    story: "Your story",
    // @patient headline
    learning: "In simple words",
    // @patient headline
    didYouKnow: "Did you know",
    // @patient phrase
    ask: "Ask",
    // @patient phrase
    family: "Family",
    // @patient phrase
    notForMe: "Not for me",
    // @patient phrase
    keepGoing: "Keep going",
    // @patient phrase
    toTablets: "See your tablets",
    // @patient
    declined: "Nura wrote down that this is not for you.",
    // @patient
    declinedToday: "You will not see this kind of card again today.",
    // @patient
    shared: "Your family can see this card now.",
    // @patient phrase
    fromPublisher: "From {publisher}",
    // @patient phrase
    whyLink: "Why am I seeing this?",
    // @patient headline
    whyTitle: "Why am I seeing this?",
    // @patient
    cannotShare: "Nura cannot send this card to your family yet.",
    // @patient
    quiet: "Nura keeps quiet at night.",
    // @patient
    quietSub: "Your cards come back in the morning.",
    // @patient
    nothingMore: "There is nothing more for you right now.",
    // @patient
    offlineSub: "These are your cards from earlier today.",
    // @patient headline
    askTitle: "Ask Nura",
    // @patient phrase
    askAbout: "About this card",
    // @patient phrase
    askLabel: "Your question",
    // @patient
    askLead: "Type it, or tap the microphone on the keyboard.",
    // @patient
    askSample1: "What was my blood pressure?",
    // @patient
    askSample1Theirs: "What was {name}'s blood pressure?",
    // @patient
    askSample2: "When is my next visit?",
    // @patient
    askSample2Theirs: "When is {name}'s next visit?",
    // @patient
    askSample3: "What are my medicines for?",
    // @patient
    askSample3Theirs: "What are {name}'s medicines for?",
    // @patient
    sourcePapers: "This comes from your papers.",
    // @patient
    sourceMedicines: "This comes from your medicines list.",
    // @patient
    sourceVisits: "This comes from your visits to the doctor.",
    // @patient
    askWithheld: "Some of the papers are not open to you.",
    // @patient
    askThinking: "Nura is looking.",
    // @patient
    lookingForToday: "Nura is looking for today's reads.",
    // @patient
    askAnswered: "Nura answered.",
    // @patient phrase
    askLookedAt: "What Nura looked at: {parts}",
    // @patient phrase
    newConversation: "New questions",
    // @patient headline
    earlierInConversation: "What you asked before",
    // @patient phrase
    back: "Back to your cards",
    // @patient
    statusHeld: "Nura kept this back from {name}.",
    // @patient
    statusSent: "This was on the page {name} sees.",
    // @patient
    statusOpened: "{name} opened this card.",
    // @patient
    statusPlayed: "{name} heard this card.",
    // @patient
    statusDismissed: "{name} tapped Not for me on this card.",
    // @patient phrase
    play: "Play",
    // @patient phrase
    watchAgain: "Watch again",
    // @patient phrase
    watchWhole: "Watch the whole video at {publisher}",
    // @patient phrase
    askOrSearch: "Ask or search",
    // @patient phrase
    filterLabel: "Where to look",
    // @patient phrase
    filterRecords: "Your papers",
    // @patient phrase
    filterWeb: "Online",
    // @patient phrase
    filterProviders: "Doctors and clinics",
    // @patient phrase
    filterVideos: "Videos",
    // @patient phrase
    search: "Search",
    // @patient phrase
    readPage: "Read the page at {publisher}",
    // @patient
    foundNothing: "Nura found nothing for this.",
    // @patient phrase
    nextVisit: "Your next visit is on {date}.",
  },
  reading: {
    // @patient headline
    title: "Your blood pressure",
    // @patient headline
    titleOther: "{patient}'s blood pressure",
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
    // @patient phrase
    photo: "Take a photo of the machine",
    // @patient
    photoLead: "Or take a photo of the machine's screen.",
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
    setUp: "Set up Nura",
    // @patient phrase
    signOut: "Sign out",
    // @patient phrase
    remindersGet: "Get reminders on this phone",
    // @patient phrase
    emergencyPrint: "Print it",
    // @patient
    remindersOn: "Reminders are on for this phone.",
    // @patient phrase
    remindersStop: "Stop reminders on this phone",
    // @patient
    remindersDenied1: "This phone said no to reminders.",
    // @patient
    remindersDenied2: "You can change that in the phone's settings.",
    // @patient headline
    areaTitle: "Where you live",
    // @patient
    areaLead: "Nura uses your town only for dengue, haze or hot weather near you.",
    // @patient
    areaNone: "Nura does not know your town.",
    // @patient
    areaIs: "Nura knows your town is {area}.",
    // @patient
    areaAsk: "Do you live in {area}?",
    // @patient phrase
    areaYes: "Yes, I live there",
    // @patient phrase
    areaNo: "No",
    // @patient phrase
    areaChange: "Choose your town",
    // @patient phrase
    areaClear: "Forget my town",
    // @patient
    areaWho: "The one who looks after your papers can see your town.",
    // @patient headline
    ramadanTitle: "Ramadan",
    // @patient
    ramadanLead: "If you fast in Ramadan, Nura can help you plan for it.",
    // @patient
    ramadanWho: "The one who looks after your papers will see this too.",
    // @patient phrase
    ramadanYes: "Yes, tell me before Ramadan",
    // @patient
    ramadanOn: "Nura will tell you before Ramadan.",
    // @patient phrase
    ramadanStop: "Stop telling me",
    // @patient headline
    whatNuraUsesTitle: "What Nura uses",
    // @patient
    whatNuraUsesLead: "Choose what Nura may use to suggest reads and videos for you.",
    // @patient
    whatNuraUsesLeadOther: "Choose what Nura may use to suggest reads and videos for {patient}.",
    // @patient phrase
    whatNuraUsesOn: "On",
    // @patient phrase
    whatNuraUsesOff: "Off",
    // @patient
    whatNuraUsesReadOnly: "Only {name} or the chief can change this.",
    whatNuraUsesFamilies: {
      // @patient phrase
      food: "What you eat",
      // @patient phrase
      sleep: "Your sleep",
      // @patient phrase
      steps: "Your steps",
      // @patient phrase
      water: "Your water",
      // @patient phrase
      search_topics: "What you ask about",
    },
    whatNuraUsesFamiliesOther: {
      // @patient phrase
      food: "What {patient} eats",
      // @patient phrase
      sleep: "{patient}'s sleep",
      // @patient phrase
      steps: "{patient}'s steps",
      // @patient phrase
      water: "{patient}'s water",
      // @patient phrase
      search_topics: "What {patient} asks about",
    },
    // @patient phrase
    insurance: "Insurance",
  },
  insurance: {
    // @patient headline
    title: "Your insurance",
    // @patient headline
    titleOther: "{patient}'s insurance",
    // @patient
    none: "Nura has no insurance written down for you yet.",
    // @patient
    noneOther: "Nura has no insurance written down for {patient} yet.",
    type: {
      // @patient phrase
      hospital: "Hospital cover",
      // @patient phrase
      outpatient: "Outpatient cover",
      // @patient phrase
      critical_illness: "Critical illness cover",
      // @patient phrase
      government_scheme: "Government scheme",
    },
    status: {
      // @patient phrase
      active: "Active",
      // @patient phrase
      lapsed: "Lapsed",
      // @patient phrase
      cancelled: "Cancelled",
    },
    // @patient
    covers: "It covers {value}.",
    // @patient
    renews: "It renews on {date}.",
    // @patient
    premiumDue: "The next payment is due on {date}.",
    // @patient
    reference: "The policy number is {reference}.",
  },
  // The visit day (E05-03, E05-04): the logistics card, the recording, the clips.
  visit: {
    // @patient headline
    title: "Your visit",
    // @patient phrase
    open: "See your next visit",
    // @patient phrase
    openOther: "See {patient}'s next visit",
    // @patient
    none: "Nura has no visit written down for you.",
    // @patient
    fromVisit: "This comes from your visits to the doctor.",
    // @patient
    onDuty: "It is {name}'s turn that day.",
    // @patient phrase
    driveYes: "Yes, {name} will drive",
    // @patient phrase
    start: "Start recording",
    // @patient
    keepOpen: "Keep this page open while Nura listens.",
    // @patient
    consentLead: "Nura needs you to say yes before it listens.",
    // @patient phrase
    saidYes: "{doctor} said yes",
    // @patient phrase
    saidNo: "{doctor} said no",
    // @patient
    listening: "Nura is listening.",
    // @patient phrase
    stop: "Stop",
    // @patient
    saving: "Nura is keeping the recording.",
    // @patient
    saved: "Nura kept the recording.",
    // @patient
    notHeard: "Nura could not hear the words.",
    // @patient
    notHeardSub: "You can listen to it in your papers.",
    // @patient
    cardLater: "Nura has not made the card yet.",
    // @patient
    stoppedAway: "Nura stopped listening when you left this page.",
    // @patient phrase
    keepHeard: "Keep what Nura heard",
    // @patient phrase
    hearClip: "Hear what {doctor} said",
    // @patient headline
    byHandTitle: "Write what {doctor} said",
    // @patient phrase
    byHandLabel: "What {doctor} said",
    // @patient phrase
    byHandSave: "Keep the notes",
    // @patient
    noMic: "Nura cannot use the microphone on this phone.",
    // @patient
    noMicSub: "You can write it down yourself instead.",
    // @patient
    noConnection: "The phone has no connection right now.",
    // @patient
    sendLater: "Nura sends the recording when the connection is back.",
    // @patient
    keepOpenToSend: "Keep this page open until then.",
  },
  // Taps made while the phone could not reach Nura (E00-08).
  held: {
    // @patient
    held: "Nura will send what you tapped when the internet is back.",
    // @patient
    tapped: "You tapped this at {time}.",
    // @patient
    sent: "Nura sent what you tapped.",
  },
  // The emergency card on the phone (E00-08). The card's own lines are the backend's.
  emergency: {
    // @patient
    asOf: "Nura last read this card on {date}.",
    // @patient
    none: "Your emergency card is not on this phone yet.",
    // @patient
    noneSub: "Open this card again later, with the internet on.",
    // @patient phrase
    callChief: "Call {name}",
    // @patient phrase
    callAmbulance: "Call the ambulance on {number}",
    // @patient phrase
    print: "Print this card",
  },
  // Papers from the photos (E18-01, the web's multi-pick in place of the photo library scan).
  papers: {
    // @patient phrase
    open: "Add papers from your photos",
    // @patient phrase
    chooseMany: "Choose many photos",
    // @patient headline
    title: "Papers from your photos",
    // @patient
    lead: "Choose all the photos of your papers together.",
    // @patient
    lead2: "Nura sends nothing until you tap Send.",
    // @patient phrase
    pick: "Choose photos",
    // @patient
    gridLead: "Tap a photo to leave it out.",
    // @patient phrase
    picture: "Paper {count}",
    // @patient
    tileIn: "Nura will send this one.",
    // @patient
    tileOut: "Nura will not send this one.",
    // @patient phrase
    sendOne: "Send 1 paper",
    // @patient phrase
    send: "Send {count} papers",
    // @patient
    sending: "Nura is sending paper {n} of {total}.",
    // @patient
    working: "Nura is working on it.",
    // @patient headline
    found: "What Nura found",
    // @patient
    read: "Nura read this paper.",
    // @patient phrase
    check: "Check this paper",
    // @patient
    notHealth: "This is not a health paper.",
    // @patient
    notSent: "The internet was off, so this one did not go.",
    // @patient phrase
    sendRest: "Send the ones that did not go",
    // @patient
    nothingKept: "Nura kept no photo on this phone.",
    // @patient phrase
    backToday: "Back to Today",
  },
  // The one player (E15-07): under anything Nura says out loud.
  player: {
    // @patient phrase
    play: "Play",
    // @patient phrase
    pause: "Pause",
    // @patient phrase
    speed: "How fast Nura speaks",
    // @patient phrase
    slower: "Slower",
    // @patient phrase
    usual: "Usual speed",
    // @patient phrase
    faster: "Faster",
    // @patient phrase
    nextPart: "Next part",
    // @patient phrase
    hearStory: "Hear about {name}",
  },
  day: {
    // @patient headline
    topThree: "3 things for today",
    // @patient phrase
    notWell: "I am not feeling well",
    // @patient phrase
    notWellShort: "Not well?",
    // @patient phrase
    notWellShortOther: "Not well?",
    // @patient headline
    notWellTitle: "Tell Nura how you feel",
    // @patient headline
    notWellTitleOther: "Tell Nura how {patient} feels",
    // @patient
    notWellLead: "Say it or type it in your own words.",
    // @patient phrase
    wordsLabel: "What you feel",
    // @patient phrase
    wordsLabelOther: "What {patient} feels",
    // @patient phrase
    send: "Tell Nura",
    // @patient phrase
    sayIt: "Say it out loud",
    // @patient phrase
    stopAndSend: "Stop and send",
    // @patient
    sending: "Nura is sending this now.",
    // @patient headline
    whatToDo: "What to do now",
    // @patient phrase
    backToday: "Back to Today",
    // @patient phrase
    symptomsOpen: "Write down how you feel",
    // @patient phrase
    notWellOther: "{patient} is not feeling well",
    // @patient phrase
    symptomsOpenOther: "Write down how {patient} feels",
    // @patient headline
    symptomsTitleSelf: "How you have felt",
    // @patient headline
    symptomsTitleOther: "How {name} has felt",
    // @patient
    symptomsLead: "Say what you feel, how bad it is and since when.",
    // @patient
    symptomsLeadOther: "Say what {patient} feels, how bad it is and since when.",
    // @patient phrase
    symptomsKeep: "Keep this",
    // @patient phrase
    sendAgain: "Send it again",
    // @patient
    symptomsSaved: "Nura wrote this down.",
    // @patient phrase
    nudgeOk: "OK",
    // @patient phrase
    nudgeWentWell: "It went well",
    // @patient phrase
    nudgeNotToday: "Not today",
    // @patient phrase
    briefOpen: "Read before your visit",
    // @patient phrase
    briefOpenOther: "Read before {patient}'s visit",
    // @patient headline
    briefTitle: "Before your visit",
    // @patient phrase
    questionsOpen: "Your questions for the doctor",
    // @patient phrase
    questionsOpenOther: "Questions for {patient}'s doctor",
    // @patient headline
    questionsTitle: "Questions for your visit",
    // @patient phrase
    costOpen: "What it may cost",
    // @patient phrase
    costOpenOther: "What {patient}'s visit may cost",
    // @patient headline
    costTitle: "What it may cost",
    // @patient phrase
    costCoveredLabel: "Your cover may pay",
    // @patient phrase
    costCoveredLabelOther: "{patient}'s cover may pay",
    // @patient phrase
    questionLabel: "Your question",
    // @patient phrase
    questionAdd: "Keep this question",
    // @patient
    questionCheck: "Is this what you want to ask?",
    // @patient phrase
    questionYes: "Yes, keep it",
    // @patient phrase
    questionRemove: "Take this question off",
    // @patient
    questionRemoveCheck: "Take this question off your list?",
    // @patient phrase
    questionRemoveYes: "Yes, take it off",
    // @patient
    questionKept: "Nura kept your question.",
    // @patient
    questionRemoved: "Nura took the question off your list.",
    // @patient
    summaryLead: "Check each line, then say yes.",
    // @patient phrase
    summaryLeaveOut: "Leave this out",
    // @patient
    summaryLeftOut: "Nura will leave this out.",
    // @patient
    summaryFromNotes: "This comes from the notes you wrote.",
    // @patient phrase
    summaryYes: "Yes, keep this card",
    // @patient
    summaryKept: "Nura kept what {doctor} said.",
    // @patient
    summaryWaiting: "This card is waiting for your yes.",
    fallback: {
      // @patient
      youDidRight: "You did right to say so.",
      // @patient action
      notSent: "Nura could not send this to your family.",
      // @patient action
      call995: "Call the ambulance now on 995.",
      // @patient action
      call999: "Call the ambulance now on 999.",
      // @patient action
      callFamily: "Call your family now.",
      // @patient action
      bad995: "If you feel very bad, call the ambulance now on 995.",
      // @patient action
      bad999: "If you feel very bad, call the ambulance now on 999.",
      // @patient
      closing: "Nura does not decide what is wrong.",
    },
  },
  onboarding: {
    // @patient phrase
    next: "Next",
    // @patient phrase
    notNow: "Not now",
    // @patient phrase
    later: "Set up later",
    // @patient phrase
    back: "Go back",
    // @patient
    saving: "Nura is writing that down.",
    about: {
      // @patient headline
      titleSelf: "A few things about you",
      // @patient headline
      titleOther: "A few things about {name}",
      // @patient
      leadSelf: "These set how Nura talks to you.",
      // @patient
      leadOther: "These set how Nura talks to {name}.",
      // @patient
      nameSelf: "What should Nura call you?",
      // @patient
      nameOther: "What should Nura call {name}?",
      // @patient phrase
      nameLabel: "The name Nura uses",
      // @patient
      languageSelf: "Which language do you want to hear?",
      // @patient
      languageOther: "Which language does {name} want to hear?",
      // @patient
      bornSelf: "When were you born?",
      // @patient
      bornOther: "When was {name} born?",
      // @patient phrase
      decade: "In the {decade}s",
      // @patient
      doctorSelf: "Which doctor do you see most?",
      // @patient
      doctorOther: "Which doctor does {name} see most?",
      // @patient phrase
      doctorLabel: "The doctor's name",
      // @patient
      doctorHint: "Nura will use this name every time.",
      // @patient
      breakfastSelf: "When do you usually have breakfast?",
      // @patient
      breakfastOther: "When does {name} usually have breakfast?",
      // @patient
      breakfastHint: "Nura ties morning tablets to breakfast.",
      // @patient phrase
      times: {
        "06:00": "At 6 in the morning",
        "06:30": "At half past 6",
        "07:00": "At 7 in the morning",
        "07:30": "At half past 7",
        "08:00": "At 8 in the morning",
        "08:30": "At half past 8",
        "09:00": "At 9 in the morning",
        "10:00": "At 10 in the morning",
      },
      // @patient
      switchSelf: {
        large_text: "Would bigger writing help you?",
        high_contrast: "Would darker writing help you read?",
        voice_on: "Should Nura read things out loud to you?",
        big_targets: "Would bigger buttons help you?",
        one_thing_per_screen: "Should Nura show one thing at a time?",
        read_back: "Should Nura say back what it understood?",
        repeat_prompts: "Should Nura remind you a second time?",
      },
      // @patient
      switchOther: {
        large_text: "Would bigger writing help {name}?",
        high_contrast: "Would darker writing help {name} read?",
        voice_on: "Should Nura read things out loud to {name}?",
        big_targets: "Would bigger buttons help {name}?",
        one_thing_per_screen: "Should Nura show {name} one thing at a time?",
        read_back: "Should Nura say back to {name} what it understood?",
        repeat_prompts: "Should Nura remind {name} a second time?",
      },
      // @patient
      densitySelf: "How much should Nura show you at once?",
      // @patient
      densityOther: "How much should Nura show {name} at once?",
      // @patient phrase
      densitySimple: "A little, kept simple",
      // @patient phrase
      densityDetailed: "Everything, in full",
      // @patient phrase
      yes: "Yes",
      // @patient phrase
      no: "No",
    },
    cloud: {
      // @patient headline
      titleSelf: "What is part of your health?",
      // @patient headline
      titleOther: "What is part of {name}'s health?",
      // @patient
      lead: "Tap each one that is part of it.",
      // @patient
      lead2: "Nura then shows what often goes with it.",
      // @patient
      lead3: "Nura only uses this to know where to look.",
      // @patient
      noted: "Nura wrote that down.",
      // @patient
      removed: "Nura took that off.",
      // @patient phrase
      more: "Show more words",
      // @patient phrase
      fewer: "Show fewer words",
      // @patient phrase
      done: "That is everything",
      // @patient
      term: "Doctors call it {term}.",
      // @patient
      countNone: "Nura has not written anything down yet.",
      // @patient
      count: "Nura has written {n} things down.",
      // @patient phrase
      tellMe: "Or just tell me",
      // @patient
      tellMeLead: "Say it in your own words.",
      // @patient phrase
      tellMeLabel: "In your own words",
      // @patient phrase
      tellMeSend: "Send",
      // @patient
      tellMeNothing: "Nura found no word above for that.",
      // @patient
      tellMeNothingSub: "Try tapping instead.",
      // @patient
      tellMeSafety: "Nura will not turn that into a word here.",
      // @patient
      tellMeSafetySub: "Please tell someone you trust, or get help now.",
    },
    asks: {
      // @patient
      lead: "Tap the one that is right for you.",
    },
    readBack: {
      // @patient headline
      title: "Here is what Nura understood",
      // @patient
      lead: "Please say if this is right.",
      // @patient
      lineOf: "This is {n} of {total}.",
      // @patient phrase
      yes: "Yes, that is right",
      // @patient phrase
      no: "No, that is not right",
      // @patient
      agreed: "Nura will keep that.",
      // @patient
      disputed: "Nura will not build on that one.",
      // @patient
      nothing: "You did not tap anything.",
      // @patient
      nothingFine: "That is fine.",
      // @patient
      nothingSub: "Your papers can fill this in.",
    },
    records: {
      // @patient headline
      titleSelf: "Now, your papers",
      // @patient headline
      titleOther: "Now, {name}'s papers",
      // @patient phrase
      photo: "Take a photo",
      // @patient phrase
      file: "Choose a file instead",
      // @patient phrase
      allPapers: "That is all my papers",
      // @patient phrase
      allDone: "That is all for today",
      // @patient
      looking: "Nura is looking at your paper.",
      // @patient headline
      reviewTitle: "What Nura read",
      // @patient
      reviewLead: "Check each line against the paper.",
      // @patient
      reviewLead2: "Change anything that is wrong.",
      // @patient
      sure: "Nura is sure of this one.",
      // @patient
      check: "Please check this one.",
      // @patient phrase
      changeLabel: "What the paper says",
      // @patient
      notANumber: "Please type the number from the paper.",
      // @patient
      cannotChange: "If this one is wrong, leave it out.",
      // @patient phrase
      leaveOut: "Leave this one out",
      // @patient phrase
      keepIn: "Keep this one",
      // @patient
      leftOut: "Nura will leave this one out.",
      // @patient
      leftOutByYou: "You left this one out.",
      // @patient phrase
      aboutThisPaper: "About this paper",
      // @patient
      checkedOn: "You checked this on {date}.",
      // @patient
      checkedOnOther: "{patient} checked this on {date}.",
      // @patient phrase
      seePaperItself: "See the paper itself",
      // @patient phrase
      askAboutPaper: "Ask about this paper",
      // @patient phrase
      looksRight: "Looks right",
      // @patient
      saved: "Nura wrote it down.",
      // @patient headline
      learnedTitle: "What Nura learned",
      // @patient
      kindLabReport: "This is a blood test.",
      // @patient
      kindMedicineLabel: "This is a medicine label.",
      // @patient
      kindDischargeLetter: "This is a hospital letter.",
      // @patient
      kindClinicSlip: "This is an appointment card.",
      // @patient
      kindHandwritten: "This is a note in a doctor's writing.",
      // @patient
      kindInsuranceLetter: "This is an insurance letter.",
      // @patient
      kindInsurancePolicy: "This is an insurance policy.",
      // @patient
      kindInsuranceClaim: "This is an insurance claim.",
      // @patient
      kindDeviceScreen: "This is the screen of a machine.",
      // @patient
      kindOther: "This is a health paper.",
      // @patient
      kindPillPhoto: "This is a photo of a pill.",
      // @patient
      kindPharmacyReceipt: "This is a pharmacy receipt.",
      // @patient
      unreadable: "Nura could not read this one.",
      // @patient
      typeIt: "Please type what the paper says.",
      // @patient
      fromPage: "Nura read this from page {page} of the paper.",
      // @patient
      kindUnknown: "Nura could not read this page.",
      // @patient
      unknownHint: "Try again with the page flat, in daylight.",
      // @patient
      dated: "The paper is dated {date}.",
      // @patient
      highRisk: "Nura takes extra care with this medicine.",
      // @patient
      pillProposal: "This looks like {medicine} — check with the pharmacist.",
      // @patient
      fromPhoto: "From the photo you added on {date}.",
      // @patient phrase
      otherLine: "Another line on the paper",
      // @patient
      valueUnreadable: "Nura could not read this line.",
      // @patient headline
      readingSomeOutside: "{n} of {m} are outside the range on the *paper.*",
      // @patient headline
      readingAllInRange: "All {m} are inside the range on the *paper.*",
      // @patient headline
      readingLinesRead: "Nura read {m} lines from your *paper.*",
      // @patient phrase
      chipOutside: "Outside range {n}",
      // @patient phrase
      chipInRange: "In range {n}",
      // @patient phrase
      chipCheck: "Check {n}",
      // @patient phrase
      flagAbove: "Above",
      // @patient phrase
      flagBelow: "Below",
      // @patient phrase
      flagInRange: "In range",
      // @patient phrase
      checkThisOne: "Check this one",
      // @patient phrase
      seeFullTable: "See the full table",
      // @patient
      fixHint: "Tap any value to change it.",
      // @patient phrase
      fixNumber: "Fix a number",
      // @patient
      nuraRead: "Nura read {value} from the paper.",
      // @patient headline
      checkSheetTitle: "Is this right?",
      // @patient phrase
      checkSheetConfirm: "That's right",
      // @patient phrase
      checkSheetConfirming: "Saving…",
      // @patient phrase
      checkSheetConfirmed: "Saved",
      // @patient
      safetyRanges: "Ranges are the ones printed on your paper.",
      // @patient
      safetyNotAdvice: "This is not a doctor's advice.",
      // @patient
      fromPageAndDate: "Nura read this from page {page}, added on {date}.",
      // @patient
      fromPaperOn: "Nura read this from the paper you added on {date}.",
      // @patient phrase
      dateAndFacility: "{date} · {facility}",
      // @patient phrase
      titleLabReport: "Blood test",
      // @patient phrase
      titleMedicineLabel: "Medicine label",
      // @patient phrase
      titleDischargeLetter: "Hospital letter",
      // @patient phrase
      titleClinicSlip: "Appointment card",
      // @patient phrase
      titleHandwritten: "Doctor's note",
      // @patient phrase
      titleInsuranceLetter: "Insurance letter",
      // @patient phrase
      titleInsurancePolicy: "Insurance policy",
      // @patient phrase
      titleInsuranceClaim: "Insurance claim",
      // @patient phrase
      titleDeviceScreen: "Machine screen",
      // @patient phrase
      titleOtherKind: "Health paper",
      // @patient phrase
      titlePillPhoto: "Pill photo",
      // @patient phrase
      titlePharmacyReceipt: "Pharmacy receipt",
      // @patient phrase
      titleUnknown: "Page",
    },
    questions: {
      // @patient headline
      titleSelf: "Your papers raised a few questions",
      // @patient headline
      titleOther: "{name}'s papers raised a few questions",
      // @patient
      lead: "Keep the ones to ask the doctor.",
      // @patient phrase
      keep: "Keep this one",
      // @patient phrase
      notThis: "Not this one",
      // @patient
      kept: "Nura will keep this one for the visit.",
      // @patient
      dropped: "Nura will leave this one out.",
      // @patient
      none: "Your papers raised no questions.",
    },
    invite: {
      // @patient headline
      title: "Who should see your papers?",
      // @patient
      lead: "Nura will let this one person in.",
      // @patient phrase
      nameLabel: "Their name",
      // @patient phrase
      phoneLabel: "Their phone number",
      // @patient phrase
      relationshipLabel: "Who they are to you",
      // @patient phrase
      relationships: {
        daughter: "Your daughter",
        son: "Your son",
        spouse: "Your husband or wife",
        sibling: "Your brother or sister",
        grandchild: "Your grandchild",
        other_family: "Someone else in your family",
        helper: "Your helper",
        friend: "Your friend",
        neighbour: "Your neighbour",
        other: "Someone else",
      },
      // @patient
      partsLead: "Tap each part they can see.",
      // @patient phrase
      parts: {
        medicines: "Your medicines",
        visits: "Your visits to the doctor",
        readings: "Your blood pressure book and your sugar numbers",
        records: "Your papers",
      },
      // @patient phrase
      seeWords: "See the words",
      // @patient
      wordsLead: "Please read these words.",
      // @patient phrase
      agree: "I agree, give them the key",
      // @patient
      done: "They can see those parts now.",
    },
    plan: {
      // @patient headline
      title: "Nura is ready",
      // @patient
      lead: "Everything you see is built from this.",
      // @patient
      cadence1: "Nura will ask for one thing a day, never more.",
      // @patient
      cadence2: "Tap Later and Nura asks once more.",
      // @patient
      missing: "Nura does not have this yet.",
      // @patient
      onDay: "Nura will ask for this on {date}.",
      // @patient phrase
      later: "Later",
      // @patient
      laterSaid: "Nura will ask once more in a few days.",
      // @patient
      moreOne: "There is 1 more after that.",
      // @patient
      more: "There are {count} more after that.",
      // @patient
      nothing: "Nura has everything it needs for now.",
      // @patient phrase
      open: "Open Nura",
    },
    // His words for the lines a paper carries, by the backend's subject then attribute code
    // (E02's fixture extractor: a lipid panel and a medicine label so far).
    // @patient phrase
    fields: {
      lipid_panel: {
        total_cholesterol: "The total cholesterol",
        hdl: "The good cholesterol",
        ldl: "The bad cholesterol",
        ldl_reference_range: "The normal range for the bad cholesterol",
        triglycerides: "The blood fats",
        vldl: "Another blood fat number",
        tc_hdl_ratio: "The cholesterol ratio",
        non_hdl_cholesterol: "The cholesterol without the good part",
      },
      blood_test: {
        hba1c: "Your sugar test",
        haemoglobin: "Your blood count",
        tsh: "Your thyroid test",
        uric_acid: "Your uric acid number",
        white_cells: "Your white blood cell number",
        platelets: "Your platelet number",
      },
      kidney_panel: {
        creatinine: "Your kidney number",
        egfr: "Your kidney filter",
        potassium: "Your body salt",
        urea: "The waste number from your kidneys",
        sodium: "The salt number in your blood",
      },
      liver_panel: {
        alt: "One of your liver numbers",
        ast: "Another of your liver numbers",
        alp: "A liver and bone number",
        ggt: "A liver and alcohol number",
        bilirubin: "The yellow colour number",
        albumin: "The protein number in your blood",
      },
      full_blood_count: { hemoglobin: "The blood count number" },
      device: { kind: "The machine" },
      blood_pressure: { systolic: "The top number", diastolic: "The bottom number" },
      heart_rate: { pulse: "The heartbeat" },
      reading: { taken_at: "When it was taken" },
      visit: { doctor: "The doctor", next_visit: "The next visit" },
      discharge: {
        admitted_on: "When you went in",
        discharged_on: "When you came home",
        reason: "Why you were in hospital",
        weight_at_discharge: "Your weight when you came home",
      },
      follow_up: { date: "When to go back" },
      hypertension: { control: "What the doctor wrote about your blood pressure" },
      blood_sugar: { glucose: "The sugar number" },
      lab_report: {
        lab: "Where the blood was tested",
        facility: "Where it was tested",
        remark: "What the report says beside the numbers",
        patient_name: "The name on the report",
        patient_id: "The patient number on the report",
        ordering_doctor: "Which doctor asked for it",
      },
      person: { birth_year: "The year of birth", sex: "Male or female" },
      medicine: {
        name: "The medicine",
        strength: "How strong it is",
        dose: "How to take it",
        frequency: "How often to take it",
        quantity: "How many were given",
        dispensed_at: "When it was given",
        prescriber: "Which doctor wrote it",
      },
      insurance_policy: {
        insurer: "The insurance company",
        policy_number: "The policy number",
        plan: "The plan",
        holder: "Who the policy is for",
        start_date: "When it started",
        end_date: "When it ends",
      },
      insurance_claim: {
        insurer: "The insurance company",
        claim_number: "The claim number",
        status: "Where the claim stands",
        amount: "The amount",
        date: "The date",
        for: "What the claim was for",
      },
      pill: {
        imprint: "What is printed on it",
        colour: "Its colour",
        shape: "Its shape",
        score_line: "Whether it can be split",
      },
      receipt: {
        pharmacy: "The pharmacy",
        currency: "The currency",
      },
      item: {
        name: "What was bought",
        quantity: "How many",
        unit_price: "The price each",
        total: "The total price",
      },
    },
  },
  // The Record (W5): the screens' own lines. Every card's words are the backend's.
  record: {
    // @patient headline
    title: "Your papers",
    // @patient headline
    titleOther: "{name}'s papers",
    // @patient headline
    medicines: "Your medicines",
    // @patient headline
    medicinesOther: "{patient}'s medicines",
    // @patient headline
    papers: "Your papers",
    // @patient headline
    papersOther: "{patient}'s papers",
    // @patient headline
    routine: "Your day",
    // @patient headline
    routineOther: "{patient}'s day",
    // @patient headline
    timeline: "Your visits",
    // @patient headline
    timelineOther: "{patient}'s visits",
    // @patient headline
    trends: "Your blood tests",
    // @patient headline
    trendsOther: "{patient}'s blood tests",
    // @patient headline
    providers: "Your doctors and clinics",
    // @patient headline
    providersOther: "{patient}'s doctors and clinics",
    // @patient headline
    changes: "What changed",
    // @patient headline
    ledger: "Your insurance ledger",
    // @patient headline
    ledgerOther: "{patient}'s insurance ledger",
    // @patient
    ledgerWithheld: "This is kept to you.",
    // @patient
    ledgerWithheldOther: "This is kept to {patient}.",
    // @patient phrase
    back: "Back to your papers",
    // @patient phrase
    backOther: "Back to {patient}'s papers",
    // @patient
    sureYes: "You said yes to this.",
    // @patient
    sureYesOther: "{patient} said yes to this.",
    // @patient
    sureRead: "Nura read this clearly.",
    // @patient
    disputed: "Someone said this is not right.",
    // @patient
    matchByNameOnly: ["Nura found this by the name on the label.", "It did not say how strong it is."],
    // @patient
    twice: "This medicine is on your list twice.",
    // @patient
    twiceOther: "This medicine is on {patient}'s list twice.",
    // @patient phrase
    aboutIt: "About this medicine",
    // @patient phrase
    add: "Add a medicine",
    // @patient headline
    storyPurpose: "What it is for",
    // @patient headline
    storyHow: "How to take it",
    // @patient headline
    storyWatch: "What to look out for",
    // @patient headline
    storyAvoid: "What to stay away from",
    // @patient headline
    storyForgot: "If you forget it",
    // @patient headline
    storyAsk: "To ask your doctor",
    // @patient phrase
    hearParts: {
      purpose: "Hear what it is for",
      how_to_take: "Hear how to take it",
      watch_out: "Hear what to look out for",
      avoid: "Hear what to stay away from",
      if_forgotten: "Hear what to do if you forget it",
      doctor_question: "Hear what to ask your doctor",
    },
    storyAskOther: "To ask {patient}'s doctor",
    // @patient
    addLead: "Take a photo of the label first.",
    // @patient
    addLead2: "Then check what Nura read.",
    // @patient phrase
    nameLabel: "The name on the label",
    // @patient phrase
    strengthLabel: "How strong it is",
    // @patient phrase
    howLabel: "How to take it",
    // @patient
    howHint: "Type it the way the label says it.",
    // @patient phrase
    countLabel: "How many are in the box",
    // @patient phrase
    doctorLabel: "The doctor's name",
    // @patient phrase
    checkIt: "Check it",
    // @patient phrase
    formLabel: "The form (tablet, capsule, inhaler…)",
    // @patient phrase
    addTypeIt: "Type it in",
    // @patient
    addTypeLead: "Tell Nura the name, then how strong and how to take it.",
    // @patient phrase
    addLooksRight: "Looks right",
    // @patient phrase
    addFix: "Fix",
    // @patient
    addWhichLead: "“{name}” is a family of medicines, not one medicine.",
    // @patient
    addWhichQuestion: "Which one is it?",
    // @patient
    addWhichHint: "The name is usually printed small on the box.",
    // @patient phrase
    addNotSure: "I'm not sure",
    // @patient
    addNotSureNote: ["Nura has kept what you sent.", "Nothing is added until you say which one it is."],
    // @patient
    addedConnection: "Added to your tablets.",
    // @patient
    addedConnectionOther: "Added to {patient}'s tablets.",
    // @patient phrase
    seeInRegistry: "See it in your tablets",
    // @patient
    addDuplicateQuestion: ["You already have this.", "Is this a new box of the same one?"],
    // @patient
    addDuplicateQuestionOther: ["{patient} already has this.", "Is this a new box of the same one?"],
    // @patient phrase
    addDuplicateYes: "Yes, say how many",
    // @patient phrase
    addDuplicateNo: "No, just checking",
    // @patient phrase
    todayKick: "Today",
    // @patient
    outcomeNew: "This is a new medicine for your list.",
    // @patient
    outcomeRefill: "This is more of a medicine you already take.",
    outcomeNewOther: "This is a new medicine for {patient}'s list.",
    // @patient
    outcomeRefillOther: "This is more of a medicine on {patient}'s list.",
    // @patient
    outcomeChange: "This label has a different amount.",
    // @patient headline
    flaggedTitle: "Before you add it",
    // @patient
    flaggedNone: "Nura found nothing on your list that goes badly with it.",
    // @patient
    flaggedNoneOther: "Nura found nothing on {patient}'s list that goes badly with it.",
    // @patient
    severity: {
      major: "This one matters a lot.",
      moderate: "This one matters.",
      minor: "This one matters a little.",
    },
    // @patient phrase
    pair: "{one} and {two}",
    // @patient phrase
    addIt: "Add it to my list",
    // @patient
    added: "Nura added it to your list.",
    // @patient
    addedOther: "Nura added it to {patient}'s list.",
    // @patient headline
    moreTitle: "More at home",
    // @patient
    moreLead: "How many more did you find at home?",
    // @patient phrase
    moreLabel: "How many more",
    // @patient phrase
    moreYes: "Yes, add them",
    // @patient
    morePhoto: "Take a photo of the medicine label first.",
    // @patient
    morePhotoWhy: "For this medicine, Nura needs to see the label.",
    // @patient
    morePhotoKept: "Nura has the photo of the medicine label.",
    // @patient phrase
    orderYes: "Yes, ask the family",
    // @patient phrase
    orderNo: "Not now",
    // @patient
    papersNone: "Nura has no papers for you yet.",
    // @patient
    papersNoneOther: "Nura has no papers for {patient} yet.",
    // @patient
    paperFrom: "This came in on {date}.",
    // @patient phrase
    paperOpen: "Look at this paper",
    // @patient phrase
    seeAllPapers: "See all your papers",
    // @patient phrase
    seeAllPapersOther: "See all of {patient}'s papers",
    // @patient phrase
    paperChipOutside: "{n} outside",
    // @patient phrase
    paperChipInRange: "All in range",
    // @patient phrase
    paperChipCheck: "Check",
    // @patient phrase
    paperChipRead: "Read",
    // @patient phrase
    paperYearGroup: "In {year}",
    // @patient phrase
    paperAskPrefill: "About my {paper} from {date} — ",
    // @patient phrase
    older: "Show older visits",
    // @patient
    papersWith: "{count} papers are with it.",
    // @patient
    paperWith: "One paper is with it.",
    // @patient
    nothingWith: "Nothing is with it yet.",
    // @patient
    factsWith: "Nura wrote down {count} things from it.",
    // @patient
    factWith: "Nura wrote down one thing from it.",
    // @patient
    since: "It started on {date}.",
    // @patient
    ended: "It ended on {date}.",
    // @patient phrase
    seeIllness: "See this illness",
    // @patient phrase
    seeDoctor: "See this doctor",
    // @patient
    endOfList: "That is everything Nura has.",
    // @patient
    status: {
      planned: "This visit is planned.",
      confirmed: "This visit is booked.",
      attended: "You went to this visit.",
      not_attended: "You did not go to this visit.",
      cancelled: "This visit was called off.",
    },
    // @patient headline
    illnessPapers: "Papers with this illness",
    // @patient headline
    illnessVisits: "Visits during this illness",
    // @patient headline
    illnessMoments: "What was written down",
    // @patient
    moments: {
      reading: "A new number was written down on {date}.",
      dose_taken: "A tablet was taken on {date}.",
      symptom: "How you felt was written down on {date}.",
      discharge: "You came home from hospital on {date}.",
      visit: "There was a visit on {date}.",
      other: "Something was written down on {date}.",
    },
    // @patient
    photoOn: "This is a photo from {date}.",
    // @patient
    letterOn: "This is a letter from {date}.",
    // @patient
    paperOn: "This is a paper from {date}.",
    // @patient phrase
    putWith: "Put a paper with this illness",
    // @patient phrase
    putThis: "Put this paper with it",
    // @patient
    putAsk: "Put this paper with this illness?",
    // @patient phrase
    putYes: "Yes, put it there",
    // @patient
    putDone: "The paper is with the illness now.",
    // @patient
    nothingToPut: "Every paper is with it already.",
    // @patient phrase
    kind: {
      doctor: "Doctor",
      clinic: "Clinic",
      hospital: "Hospital",
      pharmacy: "Pharmacy",
      lab: "A place for blood tests",
      other: "Another place",
    },
    // @patient
    visitsMany: "Nura has {count} visits here.",
    // @patient
    visitsOne: "Nura has one visit here.",
    // @patient
    lastVisit: "The last visit was on {date}.",
    // @patient
    nextVisit: "The next visit is on {date}.",
    // @patient phrase
    where: "Where it is",
    // @patient phrase
    phone: "Phone number",
    // @patient headline
    medicinesFrom: "Medicines from here",
    // @patient headline
    notesTitle: "Notes about this place",
    // @patient
    notesOnly: "Only you and the one who looks after these papers can read them.",
    // @patient phrase
    noteLabel: "A note about this place",
    // @patient phrase
    noteSave: "Keep the note",
    // @patient
    noteSaved: "Nura kept your note.",
    // @patient
    noteSavedOther: "Nura kept the note.",
    // @patient
    writtenOn: "This was written on {date}.",
    // @patient headline
    waiting: "Still waiting",
    // @patient
    trendsLead: "Choose a test to see it over time.",
    // @patient phrase
    analytes: {
      total_cholesterol: "Your cholesterol",
      ldl: "Your bad cholesterol",
      hdl: "Your good cholesterol",
      triglycerides: "Your blood fat",
      hba1c: "Your sugar test",
      creatinine: "Your kidney number",
      egfr: "Your kidney filter",
      potassium: "Your body salt",
      haemoglobin: "Your blood count",
      tsh: "Your thyroid test",
    },
    // @patient phrase
    analytesOther: {
      total_cholesterol: "{patient}'s cholesterol",
      ldl: "{patient}'s bad cholesterol",
      hdl: "{patient}'s good cholesterol",
      triglycerides: "{patient}'s blood fat",
      hba1c: "{patient}'s sugar test",
      creatinine: "{patient}'s kidney number",
      egfr: "{patient}'s kidney filter",
      potassium: "{patient}'s body salt",
      haemoglobin: "{patient}'s blood count",
      tsh: "{patient}'s thyroid test",
    },
    // A whole sentence, not a phrase: it stands alone as its own paragraph (Day.tsx), which
    // a screen reader reads as a complete unit (#166 review).
    // @patient
    resultOn: "It was {value} on {date}.",
    // Her density only (the caregiver's table of results): the unit stays with the number.
    // Never shown to him, so not a patient string; `resultOn` is his.
    resultOnUnit: "{value} {unit} on {date}",
    // @patient
    rangeUnder: "For most people this number is under {upper}.",
    // @patient
    rangeOver: "For most people this number is over {lower}.",
    // @patient
    rangeBetween: "For most people this number is {lower} to {upper}.",
    // @patient
    noRange: "Nura has no usual number for this one.",
    // @patient
    labRange: "The usual number is printed on your blood test.",
    // @patient
    guideRange: "The usual number comes from a guide for your age.",
    // @patient
    noRangeBecause: {
      needs_age: "Nura needs your age to find the usual number.",
      needs_sex: "Nura needs to know if you are a man or a woman.",
      none_on_file: "Nura has no usual number for this one.",
    },
    // @patient phrase
    anchors: {
      wake: "When you wake up",
      breakfast: "Breakfast",
      lunch: "Lunch",
      dinner: "Dinner",
      bed: "Bedtime",
    },
    // @patient phrase
    anchorsOther: {
      wake: "When {patient} wakes up",
      breakfast: "Breakfast",
      lunch: "Lunch",
      dinner: "Dinner",
      bed: "Bedtime",
    },
    // @patient phrase
    readings: {
      blood_pressure: "Blood pressure",
      blood_sugar: "Blood sugar",
      weight: "Weight",
    },
    // @patient phrase
    walk: "A walk",
    // @patient
    notSet: "Nobody has set your day yet.",
    // @patient
    notSetOther: "Nobody has set {patient}'s day yet.",
    // @patient phrase
    setDay: "Set your day",
    // @patient phrase
    setDayOther: "Set {patient}'s day",
    // @patient phrase
    timeLabel: "What time",
    // @patient phrase
    morningCard: "When the Today page comes",
    // @patient phrase
    walkAfter: "A walk after this",
    // @patient phrase
    checkDay: "Check your day",
    // @patient
    dayAsk: "Is this how your day goes?",
    // @patient
    dayAskOther: "Is this how {patient}'s day goes?",
    // @patient phrase
    dayYes: "Yes, set your day",
    // @patient
    daySaved: "Nura wrote down your day.",
    // @patient headline
    tableMoment: "When",
    // @patient headline
    tableTime: "Time",
    // @patient headline
    tableMedicines: "Medicines",
    // @patient headline
    tableReadings: "What to check",
    // @patient phrase
    ledgerTotals: "Totals for {year}",
    // @patient phrase
    ledgerClaimedLabel: "Claimed",
    // @patient phrase
    ledgerInsurerPaidLabel: "The insurance company paid",
    // @patient phrase
    ledgerPatientPaidLabel: "You paid",
    // @patient phrase
    ledgerPatientPaidLabelOther: "{patient} paid",
    // @patient
    ledgerNone: "No claims are on file yet.",
    // @patient phrase
    ledgerOn: "On {date}",
  },
  family: {
    // @patient headline
    title: "Family",
    // @patient headline
    circleSelf: "Who can see your papers",
    // @patient headline
    circleOther: "Who can see {name}'s papers",
    // @patient headline
    trailSelf: "Who looked at your papers",
    // @patient headline
    trailOther: "Who looked at {name}'s papers",
    // @patient headline
    onlyMe: "Keep a part to yourself",
    // @patient
    onlyMeLead: "Tap a part to keep it to yourself.",
    // @patient phrase
    onlyMeYes: "Yes, only me",
    // @patient phrase
    onlyMeLift: "Let them see it again",
    // @patient phrase
    onlyMeMarked: "Only you",
    // @patient headline
    consentsSelf: "What you said yes to",
    // @patient headline
    consentsOther: "What {name} said yes to",
    // @patient phrase
    stop: "Stop this",
    // @patient phrase
    stopYes: "Yes, stop it",
    // @patient phrase
    closeAccount: "Close my account",
    // @patient phrase
    closeAccountOther: "Close {name}'s account",
    // @patient phrase
    closeAccountYes: "Yes, close my account",
    // @patient phrase
    closeAccountYesOther: "Yes, close {name}'s account",
    // @patient phrase
    keepCopy: "Keep a copy to print",
    // @patient phrase
    savePage: "Save the page",
    // @patient headline
    thread: "Family messages",
    // @patient phrase
    threadEarlier: "Show the day before",
    // @patient phrase
    messageLabel: "Your message to the family",
    // @patient phrase
    sendMessage: "Send to the family",
    // @patient phrase
    sendingMessage: "Sending to the family",
    // @patient headline
    keys: "Change who can see what",
    // @patient headline
    newKey: "Give someone a key",
    // @patient phrase
    holderName: "Their name",
    // @patient phrase
    holderPhone: "Their phone number",
    // @patient phrase
    roleLabel: "Who they are",
    // @patient phrase
    partsLabel: "What they can see",
    // @patient phrase
    windowLabel: "For how long",
    // @patient phrase
    makeKey: "Make the key",
    // @patient phrase
    seeWords: "See the words",
    // @patient
    wordsLead: "Please read these words.",
    // @patient phrase
    agreeKey: "I agree, give them the key",
    // @patient phrase
    narrow: "Make it smaller",
    // @patient phrase
    narrowYes: "Yes, make it smaller",
    // @patient phrase
    closeKey: "Close this key",
    // @patient phrase
    closeYes: "Yes, close it now",
    // @patient phrase
    notNow: "Not now",
    // @patient phrase
    roles: {
      chief: "Looks after everything",
      caregiver: "Carer",
      viewer: "Can only look",
      helper: "Helper",
      emergency: "Emergency only",
      clinic: "Clinic",
    },
    // @patient phrase
    windows: {
      always: "Until stopped",
      thirty_days: "30 days",
      seventy_two_hours: "3 days",
      one_day: "1 day",
    },
    // @patient phrase
    parts: {
      medicines: "Medicines",
      visits: "Visits to the doctor",
      readings: "Blood pressure book and sugar numbers",
      records: "Papers",
      notes: "Private notes",
      money: "Insurance letters",
      emergency: "Emergency card",
      family: "Family list",
      ask: "Questions to Nura",
      send: "Messages Nura sends",
    },
    // @patient headline
    roster: "Who is on duty, and tasks",
    // @patient headline
    rosterTitle: "Who is on duty",
    // @patient phrase
    who: "Who",
    // @patient phrase
    days: "Days",
    // @patient phrase
    from: "From",
    // @patient phrase
    to: "To",
    // @patient phrase
    onDutyNow: "On duty now",
    // @patient phrase
    takeOff: "Take off the list",
    // @patient phrase
    addSlot: "Put on duty",
    // @patient headline
    tasksTitle: "Tasks",
    // @patient phrase
    taskWhat: "What to do",
    // @patient phrase
    taskDue: "By when",
    // @patient phrase
    addTask: "Give the task",
    // @patient phrase
    done: "It is done",
    // @patient phrase
    doneChip: "Done",
    // @patient phrase
    nextVisit: "See the next visit and who drives",
    // @patient headline
    messagesTitle: "Messages for {name}",
    // @patient phrase
    templates: {
      pickup: "A pick-up time",
      call_you: "A time to call",
      see_doctor: "A visit to the doctor",
      thinking_of_you: "Thinking of you",
      weigh_tomorrow: "Stand on the scale tomorrow",
      drink_water: "Drink a glass of water",
    },
    // @patient phrase
    ownWords: "My own words",
    // @patient phrase
    slots: {
      who: "Who",
      when: "When",
      doctor: "Which doctor",
      day: "Which day",
    },
    // @patient phrase
    memoLabel: "One line each",
    // @patient phrase
    languageLabel: "In which language",
    // @patient phrase
    preview: "See it as it will look",
    // @patient phrase
    sendAt: "Send from",
    // @patient phrase
    until: "Until",
    // @patient phrase
    channelApp: "In the app",
    // @patient phrase
    channelWhatsapp: "On WhatsApp",
    // @patient phrase
    schedule: "Schedule it",
    // @patient phrase
    states: {
      scheduled: "Waiting to send",
      sent: "Sent",
      not_sent: "Not sent in time",
    },
    // @patient headline
    metrics: "The week in numbers",
    // @patient phrase
    weekOf: "Week of {date}",
    // @patient phrase
    taps: "Taps",
    // @patient phrase
    fineToday: "Fine today",
    // @patient phrase
    fineShare: "Fine today, out of 100",
    // @patient phrase
    kind: "Kind",
    // @patient phrase
    handedOver: "Given",
    // @patient phrase
    accepted: "Taken up",
    // @patient phrase
    dismissed: "Put aside",
    // @patient phrase
    kinds: {
      anticipation: "Getting ready",
      check_in: "Checking in",
      pattern: "A pattern",
      commitment: "A promise",
      recognition: "Well done",
      presence: "Thinking of you",
    },
    // @patient phrase
    kindsTheirs: {
      anticipation: "Getting {name} ready",
      check_in: "Checking in on {name}",
      pattern: "A pattern in {name}'s days",
      commitment: "A promise {name} made",
      recognition: "{name} did well",
      presence: "Thinking of {name}",
    },
    // @patient headline
    calendar: "Visits from a calendar",
    // @patient phrase
    chooseFile: "Choose a calendar file",
    // @patient phrase
    agree: "I agree",
    // @patient phrase
    bookYes: "Yes, book this visit",
    // @patient phrase
    notThis: "Not this one",
    // @patient phrase
    ladderYes: "I'm on it",
    // @patient headline
    deliveries: "What Nura sent",
    // @patient headline
    settings: "When and how Nura sends",
    // @patient phrase
    triggers: {
      morning: "Morning card",
      dose: "Tablet reminder",
      reorder: "Time to buy more",
      doses_untapped: "Tablets not tapped",
      flag: "Not well",
      visit_tomorrow: "Visit tomorrow",
      papers: "Papers waiting",
      family_message: "Family message",
      first_week_prompt: "First week",
      nudge: "A small reminder",
      check_in: "How are you feeling today",
      family_notice: "What Nura wrote down this week",
    },
    // @patient phrase
    channels: {
      app_push: "App",
      whatsapp: "WhatsApp",
      caregiver: "Through the carer",
      in_app: "In the app",
    },
    // @patient phrase
    outcomes: {
      sent: "Sent",
      capped: "Held: enough for today",
      quiet: "Held: quiet hours",
      no_channel: "No way to reach them",
      no_scope: "Their key does not cover it",
      skipped: "Skipped on a quiet day",
    },
    // @patient
    skippedBecause: {
      flagOpen: "Held: something about {name} not feeling well comes first today.",
      saidToday: "Held: {name} already told Nura how things are today.",
      nudgeAsked: "Held: Nura already asked {name} how things are today.",
      questionOpen: "Held: {name} still has a question from Nura to answer.",
    },
    // @patient phrase
    rule: "Rule",
    // @patient phrase
    quietFrom: "Quiet from",
    // @patient phrase
    quietUntil: "Quiet until",
    // @patient phrase
    skipQuietDays: "On a quiet day, skip the morning card",
    // @patient phrase
    cap: "How many a day",
    // @patient phrase
    saveSettings: "Keep these settings",
    // @patient phrase
    neverHeld: "Never held",
    // @patient phrase
    everyWay: "Nura always tells your family about this, every way it can.",
    // @patient headline
    documents: "Papers for the family list",
    // @patient phrase
    tags: {
      lpa: "Lasting power of attorney",
      medical_letter: "Doctor's letter",
      consent_form: "Consent form",
    },
    // @patient phrase
    backs: {
      consent: "Backs an agreement",
      stewardship: "Backs looking after the papers",
    },
    // @patient phrase
    stillOn: "Still on",
    // @patient phrase
    stoppedChip: "Stopped",
    // @patient phrase
    addDocument: "Add a paper",
    // @patient phrase
    chooseDocument: "Choose a file or a photo",
    // @patient phrase
    whatPaper: "What kind of paper",
  },
  connect: {
    // @patient headline
    familyTitle: "Your family",
    // @patient headline
    familyTitleOther: "{patient}'s family",
    // @patient phrase
    addPerson: "Add",
    // @patient phrase
    addPersonLine: "Someone new",
    // @patient line
    noFamily: "No one has a key to your papers yet.",
    // @patient line
    noFamilyOther: "No one has a key to {patient}'s papers yet.",
    // @patient headline
    nextCallTitle: "Next call",
    // @patient phrase
    call: "Call",
    // @patient phrase
    change: "Change",
    // @patient line
    noCall: "No call is on your calendar yet.",
    // @patient line
    noCallOther: "No call with {patient} is on the calendar yet.",
    // @patient headline
    nearYouTitle: "Near you",
    // @patient headline
    nearYouTitleOther: "Near {patient}",
    // @patient line
    noNearYou: "There is nothing near you yet.",
    // @patient line
    noNearYouOther: "There is nothing near {patient} yet.",
    // @patient headline
    messagesTitle: "Messages",
    // @patient line
    noMessages: "There are no messages yet.",
    // @patient phrase
    seeAllFamily: "See everyone with a key",
    // @patient phrase
    seeAllNearYou: "See everything near you",
    // @patient phrase
    seeAllMessages: "See all messages",
    // @patient headline
    callsTitle: "Calls",
    // @patient phrase
    scheduleCall: "Schedule a call",
    // @patient phrase
    cancelCallButton: "Cancel this call",
    // @patient line
    cancelledCall: "This call is cancelled.",
    // @patient phrase
    personLabel: "Who",
    // @patient phrase
    whenLabel: "When",
    // @patient phrase
    linkLabel: "Call link, if there is one",
    // @patient phrase
    callLabelLabel: "What to call it",
  },
  visitSuggest: {
    // @patient phrase
    followUpWhy: "From your hospital letter",
    // @patient phrase
    medicineReviewWhy: "From your medicines",
    // @patient phrase
    testComingWhy: "From your blood test",
    // @patient phrase
    screeningDueWhy: "From your papers",
    // @patient
    rowOther: "Nura suggests {name} sees the doctor.",
    // @patient phrase
    bookIt: "Book it",
    // @patient phrase
    notNow: "Not now",
  },
  review: {
    // @patient headline
    title: "Pharmacist's queue",
    // @patient phrase
    tokenLabel: "Staff token",
    // @patient phrase
    open: "Open the queue",
    // @patient headline
    statusTitle: "The first 50 of each card",
    // @patient phrase
    cardType: "Card",
    // @patient phrase
    sampled: "Kept",
    // @patient phrase
    pending: "Waiting",
    // @patient phrase
    stillToCheck: "Still to check",
    // @patient phrase
    sourcesWaiting: "Sources waiting: {count}",
    // @patient headline
    queueTitle: "Waiting for a decision",
    // @patient phrase
    showPending: "Only waiting",
    // @patient phrase
    showAll: "Everything",
    // @patient phrase
    approve: "Approve",
    // @patient phrase
    reject: "Reject",
    // @patient phrase
    reasonLabel: "Why",
    // @patient phrase
    rewrite: "Rewrite the lines",
    // @patient phrase
    headline: "Headline",
    // @patient phrase
    body: "Lines",
    // @patient phrase
    voice: "Spoken lines",
    // @patient phrase
    why: "Why this card",
    // @patient phrase
    saveRewrite: "Keep as a proposal",
    // @patient phrase
    decided: "Decided",
    // @patient phrase
    leave: "Close the queue",
  },
  errors: {
    // @patient
    network: "Nura cannot reach the internet right now.",
    // @patient phrase
    tryAgain: "Try again",
  },
  chief: {
    // @patient headline
    sentTitle: "Sent to {name} this week",
    // @patient
    sentNone: "Nura sent nothing to {name} this week.",
    // @patient headline
    watchingTitle: "Watching for {name}",
    // @patient
    watchingNone: "Nura is not watching for anything yet.",
    // @patient
    sourcesNote: "Nura reads only health offices, hospitals and doctors' groups.",
    // @patient phrase
    onChange: "When something new comes in",
    // @patient phrase
    daily: "Every day",
    // @patient phrase
    weekly: "Every week",
    // @patient phrase
    beforeVisits: "Before each visit",
    // @patient phrase
    once: "Once",
    // @patient phrase
    paused: "Paused",
    // @patient phrase
    pause: "Pause",
    // @patient phrase
    resume: "Start again",
    // @patient phrase
    pauseWatch: "Stop watching for this for now",
    // @patient phrase
    add: "Watch for something new",
    // @patient
    addLead: "Choose what Nura should watch for.",
    // @patient
    added: "Nura will watch for this from now on.",
    // @patient phrase
    dengue: "Dengue",
    // @patient phrase
    haze: "Haze",
    // @patient phrase
    heat: "Hot weather",
    // @patient phrase
    festiveFood: "Festive food",
  },
  // One plain sentence for each way the backend says no, by the refusal's class name
  // (`backend/app/channels/api/refusals.py`). The name itself is never shown.
  // @patient
  refusals: {
    // @patient
    FastingIsHisToSay: "Only the owner can say this.",
    // @patient
    NotAClipCard: "This card has nothing to play.",
    // @patient
    NoExcerpt: "Nura reads this picture out loud.",
    // @patient
    NoClipRenderer: "Nura cannot show this picture right now.",
    // @patient
    SecondsOnlyOnAPlay: "Nura could not write this down.",
    // @patient
    NotACadence: "Please choose how often from the list.",
    // @patient
    NotAHazard: "Nura can watch for dengue, haze or hot weather.",
    // @patient
    NotASeason: "Nura can watch for Ramadan or festive food.",
    // @patient
    NotACoarseArea: ["Please choose your town from the list.", "Or type only the start of your postcode."],
    // @patient
    OnlyHeSetsHisArea: "Only the owner can choose the town.",
    // @patient
    NotAFilter: "Please choose where to look.",
    // @patient
    NothingToFind: "Please type a word to look for.",
    // @patient
    NotTheirsToManage: ["Only the owner can do this.", "The one who looks after these papers can too."],
    default: "Nura could not do that right now.",
    NotInTheDemo: ["This demo only takes test phone numbers.", "A test number starts with +65 0."],
    CardsStillOpen: "A paper still waits for your yes.",
    NotAtThisStep: "That step comes a little later.",
    BiographyClosed: "This setting-up is already finished.",
    PaperAlreadyAdded: "That paper is already with the others.",
    NotTheirsToSetUp: "Only the owner or his family can set this up.",
    NotADecade: "Please choose a decade from the list.",
    NotALanguage: "Nura does not speak that language yet.",
    NoPlan: "Nura has nothing to ask for yet.",
    NotPlainEnough: "Please write the question in plain words.",
    HolderNeedsAName: "Please type the name of the person you are letting in.",
    NotAPdf: "That file is not one Nura can read.",
    PdfTooLarge: "That file is too big for Nura.",
    UnreadableField: "Please type the line Nura could not read.",
    NotEveryFieldDecided: "Please check every line first.",
    NotADecision: "Nura did not understand that answer.",
    NoSuchReviewField: "That line is not on the card any more.",
    NoSession: "Please sign in again.",
    NoOpenChallenge: "Ask for a new code first.",
    WrongCode: "That code is not right.",
    ChallengeExpired: "That code is too old now.",
    ChallengeLocked: "Ask for a new code and start again.",
    NoKey: "You cannot see these papers any more.",
    AccountClosing: "Nura has stopped keeping these papers.",
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
    NoSuchItem: "That card is not here any more.",
    NoCachedPage: "Nura has not kept a page for you yet.",
    NotACursor: "Nura could not find the next card.",
    NotAConsultRecording: "Nura could not keep that recording.",
    ConsultTooLong: "That recording is too long for Nura.",
    NoSuchRecording: "That recording is not here any more.",
    NotAClip: "Nura cannot find that part of the recording.",
    OnlyTheFamilyHears: "Only the owner and the family he let in can hear this.",
    ChunkTooLarge: "That part of the recording is too big for Nura.",
    UploadClosed: "Nura is not keeping this recording any more.",
    NotYourUpload: "Only the phone that started the recording can send it.",
    NoYesFromTheDoctor: "Nura keeps a recording only after the doctor says yes.",
    NoSuchUpload: "Nura cannot find that recording.",
    NotTheirsToChangeVisits: "You can see the visits but not change them.",
    NotAChief: ["Only the owner can do this.", "The one who looks after these papers can too."],
    NotOnThisVisit: "Nura cannot give this drive to that person.",
    TapNotToday: "Nura writes down only what you tapped today.",
    // A body too large to take, answered for the app by a layer in front of it (a bare 413).
    TooLarge: "That file is too big for Nura.",
    NoteNamesHealth: "Nura cannot keep a note that names a medicine or an illness.",
    NotAPlaceNote: "Please write one short line about the place.",
    NotTheirsToSet: "You can see the day but not change it.",
    NotARoutine: "The times must go in order through the day.",
    NoSuchAnalyte: "Nura does not know that test.",
    NobodyToAsk: ["Nobody is on the family list to ask.", "Add someone to the family list first."],
    NotACount: "Please type how many, as a number.",
    AlreadyHangsThere: "That paper is already there.",
    EpisodeAlreadyClosed: "This illness is over.",
    NoSuchEpisode: "That illness is not here any more.",
    NoSuchProvider: "That doctor is not in your list.",
    StaleState: ["Nura is still catching up.", "Please try again."],
    NotIdentified: "Nura could not find this medicine.",
    StrengthNotRead: [
      "Nura found the medicine but not how strong it is.",
      "Take another photo showing how strong it is.",
    ],
    DoseNotRead: "Please type how to take it, as the label says.",
    NotADose: "Nura did not understand how to take it.",
    WouldWiden: ["Nura cannot make this wider.", "The owner must agree to more first."],
    NothingToNarrow: "That would change nothing.",
    NotTheDoer: "Only the person it is for can say it is done.",
    AlreadyDone: "This is already done.",
    NotTheOwner: "Only the owner can do this.",
    AlreadyMarked: "This part is already kept to the owner.",
    NotMarked: "This part is already open.",
    NotAPartToMark: "The emergency card is always open to the family.",
    NotOwnerOrChief: ["Only the owner can see this.", "The one who looks after these papers can too."],
    NotStaff: "Only Nura's pharmacist can open this.",
    NoSuchSlot: "That turn is not on the list any more.",
    NoSuchTask: "That task is not here any more.",
    NotADuty: "Please choose the days and the times.",
    NotOnThisProfile: "That person cannot see these papers.",
    NoSuchTemplate: "Nura does not have that message.",
    MissingSlot: "Please fill in every part of the message.",
    NotAMemo: "Please write 1 to 6 short lines.",
    BadWindow: "Please choose a time that has not passed.",
    NotPlainWords: "Please use plainer words.",
    NotAMessage: "Please write a short message.",
    NotTheirsToConnect: ["Only the owner can add a calendar.", "The one who looks after these papers can too."],
    NotTheirsToDecide: "You can see these visits but not decide them.",
    AlreadyDecided: "Someone already answered this one.",
    NoSuchConnector: "Please add the calendar file again.",
    NoSuchProposal: "That visit is not here any more.",
    NotACalendar: "Nura cannot read that calendar file.",
    ConsentRevoked: "The owner stopped this.",
    ConsentOutOfDate: "The owner must agree to the new words first.",
    AlreadyReviewed: "Someone already decided this one.",
    NoSuchReviewItem: "That item is not in the queue any more.",
    NotWellFormed: "Nura did not understand that.",
    AlertsAreNeverHeld: "A message that cannot wait is never held.",
    AlertsGoEveryWay: "Nura always tells your family about this, every way it can.",
    MessageNamesAMedicine: ["A message cannot name a medicine or say how much to take.", "Nura sends medicine reminders only from the medicines list."],
    NotOnTheLadder: "Nura did not ask you about this one.",
    NotADocument: "Nura can only keep a file or a photo here.",
    StopsByClosingTheAccount: "To stop Nura keeping your papers, close your account.",
    DocumentTooLarge: "That file is too big for Nura.",
    CalendarTooLarge: "That calendar file is too big for Nura.",
  },
} satisfies Strings;
