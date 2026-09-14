import type { Strings } from "./types";

/** Chinese: a first translation awaiting a native speaker's pass, like the backend's. */
export const zh = {
  // @patient headline
  appName: "Nura",
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
    codeLead: "我们已把验证码发到您的手机。",
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
    linkLead: "我们已把链接发到您的电邮。",
    // @patient
    linkHint: "请把电邮里的验证码贴在这里。",
    // @patient phrase
    linkLabel: "电邮里的验证码",
    // @patient
    never: "Nura 绝不会打电话向您要验证码。",
    // @patient
    wait: "请稍等。",
    // @patient phrase
    back: "返回",
  },
  doors: {
    // @patient headline
    title: "这是给谁用的？",
    // @patient phrase
    forMe: "给我自己",
    // @patient
    forMeLine: "Nura 会保存您自己的记录。",
    // @patient phrase
    forSomeone: "给别人",
    // @patient
    forSomeoneLine: "您会替他们照看他们的记录。",
    // @patient phrase
    invited: "有人让我进来",
    // @patient
    invitedLine: "{name} 和您分享了一份记录。",
    // @patient phrase
    waiting: "有一份记录在等您",
    // @patient
    waitingLine: "{name} 为您设好了它。",
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
    title: "这份记录是您的",
    // @patient
    setUpBy: "{name}（{relationship}）为您设好了它。",
    // @patient
    keepsSeeing: "{name} 会继续看到这些部分：",
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
    create: "设好它",
  },
  switcher: {
    // @patient headline
    title: "谁的记录？",
    // @patient phrase
    own: "您自己的记录",
    // @patient
    roleOwner: "这是您自己的记录。",
    // @patient
    roleChief: "您照看这份记录。",
    // @patient
    roleCaregiver: "您可以看这份记录的一部分。",
    // @patient
    roleSteward: "这是您替他们设好的。",
    // @patient
    roleOther: "您可以看这份记录。",
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
    tookMorning: "您今天早上吃了。",
    // @patient
    tookAfternoon: "您今天下午吃了。",
    // @patient
    tookEvening: "您今天傍晚吃了。",
    // @patient
    tookNight: "您今晚吃了。",
    // @patient
    allTaken: "今天的药您都吃了。",
    // @patient
    allTakenSub: "今天没有别的要吃了。",
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
    // @patient phrase
    readingButton: "记下来",
    // @patient
    stateStable: "您今天很平稳。",
    // @patient
    stateWatch: "有一件事要留意。",
    // @patient
    stateAct: "今天有一件事要做。",
    // @patient
    boundary1: "这不是医生的意见。",
    // @patient
    boundary2: "请问您的医生。",
    // @patient
    proud: "您已经有 {count} 天吃了药。",
    // @patient
    proudOne: "您已经有 1 天吃了药。",
    // @patient
    proudNone: "您第一次按“吃了”会记在这里。",
    // @patient
    proudSub: "这个数字只会往上走。",
    // @patient headline
    supplyTitle: "您的药",
    // @patient
    offline: "您现在没有网络。",
    // @patient
    offlineSub: "这是您早些时候的今日页面。",
    // @patient
    homeScreen1: "您可以把 Nura 加到主屏幕。",
    // @patient
    homeScreen2: "点“分享”，再点“添加到主屏幕”。",
    // @patient
    fromToday: "来自您的今日页面。",
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
    patient: "大而简单",
    // @patient phrase
    caregiver: "小而完整",
    // @patient phrase
    switchProfile: "看另一份记录",
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
    NoSession: "请重新登录。",
    NoOpenChallenge: "请先要一个新的验证码。",
    WrongCode: "这个验证码不对。",
    ChallengeExpired: "这个验证码太旧了。",
    ChallengeLocked: "这个验证码试了太多次。",
    NoKey: "您不能再看这份记录了。",
    OutOfScope: "记录的这部分没有对您开放。",
    OutOfRegion: "这份记录保存在另一个国家。",
    NotTheirsToRead: "只有记录的主人可以看这个。",
    NotTheirKeyToCut: "只有记录的主人可以分享这份记录。",
    NoSuchHolder: "Nura 不认识那个人。",
    NoConsent: "记录的主人还没有同意这件事。",
    ConsentWithheld: "记录的主人还没有同意这件事。",
    NotTheirConsentToGive: "只有记录的主人可以同意这件事。",
    NotTheirConsentToWithdraw: "只有记录的主人可以停止这件事。",
    NotTheClaimant: "这份记录是为别人设的。",
    NotTheirsToChange: "您可以看这些药，但不能改。",
    NoConsentToWithdraw: "没有什么可以停止的。",
    NoKeyToClose: "这个分享已经停了。",
    NoStewardshipHere: "没有人替别人设过这份记录。",
    NoState: "Nura 还没有东西可以给您看。",
    NoSuchReviewCard: "那张卡已经不在这里了。",
    NoSuchLine: "那个药不在您的单子上。",
    PhotoTooLarge: "这张照片对 Nura 来说太大了。",
    ProfileAlreadyOwned: "您已经有自己的记录了。",
    AlreadyConfirmed: "您已经同意过这件事了。",
    AlreadyRecorded: "Nura 已经有这个了。",
    AlreadyRegistered: "这个号码已经注册过了。",
    AlreadySetUp: "这个号码的记录已经设好了。",
    WaitingToBeClaimed: "有一份记录在等您领取。",
    NotTheCurrentWording: "这些话在您读过之后改过了。",
    WordingNotOnFile: "Nura 没有这些话。",
    NotWhatWasConfirmed: "这不是您同意的那件事。",
    NotAConfirmerHere: "只有您可以同意这件事。",
    HighRiskNeedsLabelPhoto: "这个药需要先拍一张标签的照片。",
    NoProvenance: "Nura 需要知道这是从哪里来的。",
    NoWordsInThatLanguage: "Nura 还没有这些话的那种语言版本。",
    NotAPhoto: "Nura 在这里只能收照片。",
    NothingBehindTheBasis: "Nura 需要知道您为什么替他们做这件事。",
    NotAgreedPerPerson: "记录的主人还没有同意让这个人进来。",
  },
} satisfies Strings;
