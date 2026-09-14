import type { Strings } from "./types";

/** Chinese: a first translation awaiting a native speaker's pass, like the backend's. */
export const zh = {
  // @patient headline
  appName: "Nura",
  demo: {
    // @patient headline
    banner: "演示版 — 不用于真实的健康信息",
    // @patient
    lines: ["这是演示版。", "请不要输入真实的健康信息。", "这里的一切每晚都会清除。"],
  },
  tabs: {
    // @patient headline
    today: "今天",
    // @patient headline
    me: "我",
  },
  signIn: {
    // @patient headline
    title: "登录",
    // @patient
    phoneLead: "请输入您的手机号码。",
    // @patient
    phoneHint: "请先输入国家代码。",
    // @patient
    nameLead: "Nura 该怎么称呼您？",
    // @patient phrase
    phoneLabel: "您的手机号码",
    // @patient phrase
    nameLabel: "您的名字",
    // @patient phrase
    sendCode: "发验证码给我",
    // @patient phrase
    useEmail: "改用电邮登录",
    // @patient phrase
    usePhone: "改用手机号码登录",
    // @patient
    codeLead: "Nura 已把验证码发到您的手机。",
    // @patient
    codeHint: "请输入短信里的 6 个数字。",
    // @patient
    codeWorks: "验证码在 10 分钟内有效。",
    // @patient phrase
    codeLabel: "验证码",
    // @patient phrase
    signInButton: "登录",
    // @patient
    emailLead: "请输入您的电邮地址。",
    // @patient phrase
    emailLabel: "您的电邮",
    // @patient phrase
    sendLink: "发链接给我",
    // @patient
    linkLead: "Nura 已把链接发到您的电邮。",
    // @patient
    linkHint: "请输入电邮里的验证码。",
    // @patient phrase
    linkLabel: "电邮里的验证码",
    // @patient
    never: "Nura 绝不会打电话向您要验证码。",
    // @patient phrase
    back: "返回",
  },
  doors: {
    // @patient headline
    title: "这是给谁用的？",
    // @patient phrase
    forMe: "给我自己",
    // @patient
    forMeLine: "Nura 会保存您自己的文件。",
    // @patient phrase
    forSomeone: "给别人",
    // @patient
    forSomeoneLine: "您会替他们照看他们的文件。",
    // @patient phrase
    invited: "有人让我进来",
    // @patient
    invitedLine: "{name} 和您分享了一份文件。",
    // @patient phrase
    waiting: "有一份文件在等您",
    // @patient
    waitingLine: "{name} 为您准备好了这些文件。",
  },
  consent: {
    // @patient headline
    title: "开始之前",
    // @patient
    lead: "请读一读这些话。",
    // @patient phrase
    agree: "我同意",
    // @patient phrase
    language: "您的语言",
  },
  claim: {
    // @patient headline
    title: "这些文件是您的",
    // @patient
    setUpBy: "{name}（{relationship}）为您准备好了这些文件。",
    // @patient
    keepsSeeing: "{name} 会继续看到您文件的这些部分：",
    // @patient phrase
    mine: "是，这是我的",
  },
  forSomeone: {
    // @patient headline
    title: "您在为谁设置？",
    // @patient
    lead: "请输入他们的名字和手机号码。",
    // @patient phrase
    theirName: "他们的名字",
    // @patient phrase
    theirPhone: "他们的手机号码",
    // @patient phrase
    relationshipLabel: "他们是您的谁",
    // @patient
    asked: "是他们请您这么做的。",
    // @patient phrase
    create: "设好文件",
  },
  switcher: {
    // @patient headline
    title: "谁的文件？",
    // @patient phrase
    own: "您自己的文件",
    // @patient
    roleOwner: "这是您自己的文件。",
    // @patient
    roleChief: "您照看这份文件。",
    // @patient
    roleCaregiver: "您可以看这份文件的一部分。",
    // @patient
    roleSteward: "这是您替他们设好的文件。",
    // @patient
    roleOther: "您可以看这份文件。",
  },
  today: {
    // @patient headline
    now: "现在",
    // @patient headline
    forYou: "今天给您的",
    // @patient headline
    greetingMorning: "早上好，{name}。",
    // @patient headline
    greetingAfternoon: "下午好，{name}。",
    // @patient headline
    greetingEvening: "晚上好，{name}。",
    // @patient phrase
    taken: "吃了",
    // @patient
    tookMorning: "您今天早上的药吃了。",
    // @patient
    tookAfternoon: "您今天下午的药吃了。",
    // @patient
    tookEvening: "您今天傍晚的药吃了。",
    // @patient
    tookNight: "您今晚的药吃了。",
    // @patient
    allTaken: "今天的药您都吃了。",
    // @patient
    allTakenSub: "今天没有别的要吃了。",
    // @patient
    nothingNow: "现在没有要吃的药。",
    // @patient
    noMedicines: "Nura 还没有您的药。",
    // @patient
    noMedicinesSub: "您的家人可以从药盒标签把药加进来。",
    // @patient phrase
    hear: "听",
    // @patient headline
    readingTitle: "您的血压",
    // @patient
    readingLead: "把今天早上的数字记下来。",
    // @patient
    readingLeadEvening: "把今晚的数字记下来。",
    // @patient phrase
    aTablet: "您的药",
    // @patient headline
    earlierTitle: "今天早些时候的",
    // @patient phrase
    readingButton: "记下来",
    // @patient
    stateStable: "您今天很平稳。",
    // @patient
    stateWatch: "Nura 在替您留意一件事。",
    // @patient
    stateWatchSub: "今天不用担心。",
    // @patient
    stateAct: "今天有一件事要做。",
    // @patient
    stateActSub: "就是这页最上面的那张卡。",
    // @patient
    staleState: "这是今天早些时候的。",
    // @patient action
    callChief: "现在就打电话给 {name}。",
    // @patient action
    callFamily: "现在就打电话给您的家人。",
    // @patient
    proud: "您已经有 {count} 天吃了药。",
    // @patient
    proudOne: "您已经有 1 天吃了药。",
    // @patient
    proudNone: "您按一次“吃了”，这个数字就变成 1。",
    // @patient
    proudSub: "这个数字只会往上走。",
    // @patient headline
    supplyTitle: "您的药",
    // @patient headline
    todayList: "您今天的药",
    // @patient
    offline: "Nura 现在连不上网络。",
    // @patient
    offlineSub: "这是您早些时候的“今天”页面。",
    // @patient
    asOf: "Nura 最后一次读您的文件是在 {date} {time}。",
    // @patient
    cannotReach: "Nura 现在联系不上您的文件。",
    // @patient headline
    emergencyTitle: "紧急卡",
    // @patient
    emergencySoon: "Nura 会把您的紧急卡放在这里。",
    // @patient
    homeScreen1: "您可以把 Nura 加到主屏幕。",
    // @patient
    homeScreen2: "点屏幕下面的“分享”。",
    // @patient
    homeScreen3: "再点“添加到主屏幕”。",
    // @patient
    fromToday: "来自您的“今天”页面。",
    // @patient
    fromState: "Nura 在 {date} 算出了这个。",
    // @patient
    fromDays: "Nura 数了您吃药的天数。",
  },
  feed: {
    // @patient headline
    title: "更多给您的",
    // @patient phrase
    open: "看更多给您的",
    // @patient headline
    story: "您的故事",
    // @patient headline
    learning: "简单地说",
    // @patient phrase
    ask: "问",
    // @patient phrase
    family: "家人",
    // @patient phrase
    notForMe: "不适合我",
    // @patient phrase
    keepGoing: "继续",
    // @patient phrase
    toTablets: "看您的药",
    // @patient
    declined: "Nura 记下了：这个不适合您。",
    // @patient
    declinedToday: "今天不会再给您看这类卡。",
    // @patient
    shared: "您的家人现在能看到这张卡。",
    // @patient
    cannotShare: "Nura 还不能把这张卡发给您的家人。",
    // @patient
    quiet: "晚上 Nura 不打扰您。",
    // @patient
    quietSub: "早上您的卡会回来。",
    // @patient
    nothingMore: "现在没有更多给您的了。",
    // @patient
    offlineSub: "这些是您今天早些时候的卡。",
    // @patient headline
    askTitle: "问 Nura",
    // @patient phrase
    askAbout: "关于这张卡",
    // @patient phrase
    askLabel: "您的问题",
    // @patient
    askLead: "打字，或者点键盘上的麦克风。",
    // @patient
    sourcePapers: "这来自您的文件。",
    // @patient
    sourceMedicines: "这来自您的药单。",
    // @patient
    sourceVisits: "这来自您看医生的安排。",
    // @patient
    askWithheld: "有些文件没有对您开放。",
    // @patient phrase
    back: "回到您的卡",
    // @patient
    statusHeld: "Nura 没有把这张卡给 {name} 看。",
    // @patient
    statusSent: "这张卡在 {name} 看的页面上。",
    // @patient
    statusOpened: "{name} 打开了这张卡。",
    // @patient
    statusDismissed: "{name} 按了“不适合我”。",
  },
  reading: {
    // @patient headline
    title: "您的血压",
    // @patient
    lead: "请输入血压机上的两个数字。",
    // @patient phrase
    top: "上面的数字",
    // @patient phrase
    bottom: "下面的数字",
    // @patient phrase
    save: "保存",
    // @patient
    saved: "Nura 记下来了。",
    // @patient phrase
    cancel: "先不要",
  },
  me: {
    // @patient headline
    title: "我",
    // @patient
    signedInAs: "您以 {name} 的身份登录了。",
    // @patient phrase
    language: "您的语言",
    // @patient phrase
    en: "English",
    // @patient phrase
    ms: "Bahasa Melayu",
    // @patient phrase
    zh: "中文",
    // @patient phrase
    look: "Nura 的样子",
    // @patient phrase
    patient: "字大，简单",
    // @patient phrase
    caregiver: "字小，一页看得多",
    // @patient phrase
    lookAuto: "让 Nura 来选",
    // @patient phrase
    switchProfile: "看别人的文件",
    // @patient phrase
    signOut: "退出登录",
  },
  errors: {
    // @patient
    network: "Nura 现在连不上网络。",
    // @patient phrase
    tryAgain: "再试一次",
  },
  // @patient
  refusals: {
    default: "Nura 现在做不了这件事。",
    NotInTheDemo: ["演示版只接受测试电话号码。", "测试号码以 +65 0 开头。"],
    NoSession: "请重新登录。",
    NoOpenChallenge: "请先要一个新的验证码。",
    WrongCode: "这个验证码不对。",
    ChallengeExpired: "这个验证码太旧了。",
    ChallengeLocked: "请要一个新的验证码，重新开始。",
    NoKey: "您不能再看这份文件了。",
    OutOfScope: "文件的这部分没有对您开放。",
    OutOfRegion: "这份文件保存在另一个国家。",
    NotTheirsToRead: "只有文件的主人可以看这个。",
    NotTheirKeyToCut: "只有文件的主人可以分享这份文件。",
    NoSuchHolder: "Nura 不认识那个人。",
    NoConsent: "文件的主人还没有同意这件事。",
    ConsentWithheld: "文件的主人暂时还没有同意。",
    NotTheirConsentToGive: "只有文件的主人可以同意这件事。",
    NotTheirConsentToWithdraw: "只有文件的主人可以停止这件事。",
    NotTheClaimant: "这份文件是为别人设的。",
    NotTheirsToChange: "您可以看这些药，但不能改。",
    NoConsentToWithdraw: "没有什么可以停止的。",
    NoKeyToClose: "这个分享已经停了。",
    NoStewardshipHere: "这些文件不是替别人设的。",
    NoState: "Nura 还没有东西可以给您看。",
    NoSuchReviewCard: "那张卡已经不在这里了。",
    NoSuchLine: "那个药不在您的单子上。",
    PhotoTooLarge: "这张照片对 Nura 来说太大了。",
    ProfileAlreadyOwned: "您已经有自己的文件了。",
    AlreadyConfirmed: "您已经同意过这件事了。",
    AlreadyRecorded: "Nura 已经有这个了。",
    AlreadyRegistered: "这个号码已经注册过了。",
    AlreadySetUp: "这个号码的文件已经设好了。",
    WaitingToBeClaimed: "有一份文件在等您说它是您的。",
    NotTheCurrentWording: "这些话在您读过之后改过了。",
    WordingNotOnFile: "Nura 没有这些话。",
    NotWhatWasConfirmed: "这不是您同意的那件事。",
    NotAConfirmerHere: "只有您可以同意这件事。",
    HighRiskNeedsLabelPhoto: "请先拍一张药盒标签的照片。",
    NoProvenance: "Nura 需要知道这是从哪里来的。",
    NoWordsInThatLanguage: "Nura 还不会用那种语言说这些话。",
    NotAPhoto: "Nura 在这里只能收照片。",
    NothingBehindTheBasis: "Nura 需要知道您为什么替他们做这件事。",
    NotAgreedPerPerson: "文件的主人还没有同意让这个人进来。",
    NotForYourself: "请走另一扇门，保存您自己的文件。",
    ConfirmationExpired: ["那个“同意”太旧了。", "请再同意一次。"],
    AlreadySpent: "您已经同意过这件事了。",
    NoSuchItem: "那张卡已经不在这里了。",
    NoCachedPage: "Nura 还没有为您保存页面。",
    NotACursor: "Nura 找不到下一张卡。",
  },
} satisfies Strings;
