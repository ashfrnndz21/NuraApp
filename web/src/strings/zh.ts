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
    record: "文件",
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
    learning: "用简单的话说",
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
    // @patient phrase
    photo: "给机器拍照",
    // @patient
    photoLead: "或者给机器的屏幕拍一张照片。",
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
    setUp: "设置 Nura",
    // @patient phrase
    signOut: "退出登录",
  },
  // The visit day (E05-03, E05-04): the logistics card, the recording, the clips.
  visit: {
    // @patient headline
    title: "您的看诊",
    // @patient phrase
    open: "看您下一次看诊",
    // @patient
    none: "Nura还没有记下您的看诊。",
    // @patient
    fromVisit: "这来自您看医生的安排。",
    // @patient
    onDuty: "那天轮到{name}。",
    // @patient phrase
    driveYes: "好，{name}开车",
    // @patient phrase
    start: "开始录音",
    // @patient
    keepOpen: "Nura听的时候，请不要离开这一页。",
    // @patient
    consentLead: "Nura听之前，需要您同意。",
    // @patient phrase
    saidYes: "{doctor}说可以",
    // @patient phrase
    saidNo: "{doctor}说不行",
    // @patient
    listening: "Nura正在听。",
    // @patient phrase
    stop: "停止",
    // @patient
    saving: "Nura正在保存录音。",
    // @patient
    saved: "Nura已经保存了录音。",
    // @patient
    notHeard: "Nura听不清说了什么。",
    // @patient
    notHeardSub: "您可以在您的文件里再听。",
    // @patient
    cardLater: "Nura还不能做出这张卡。",
    // @patient
    stoppedAway: "您离开这一页时，Nura停止了听。",
    // @patient phrase
    keepHeard: "保存Nura听到的",
    // @patient phrase
    hearClip: "听{doctor}说了什么",
    // @patient headline
    byHandTitle: "写下{doctor}说的话",
    // @patient phrase
    byHandLabel: "{doctor}说的话",
    // @patient phrase
    byHandSave: "保存笔记",
    // @patient
    noMic: "Nura不能使用这部手机的麦克风。",
    // @patient
    noMicSub: "您可以自己写下来。",
  },
  onboarding: {
    // @patient phrase
    next: "下一步",
    // @patient phrase
    notNow: "现在不用",
    // @patient phrase
    later: "以后再设",
    // @patient phrase
    back: "返回",
    // @patient
    saving: "Nura 正在记下来。",
    about: {
      // @patient headline
      titleSelf: "关于您的几件事",
      // @patient headline
      titleOther: "关于 {name} 的几件事",
      // @patient
      leadSelf: "这些决定 Nura 怎样跟您说话。",
      // @patient
      leadOther: "这些决定 Nura 怎样跟 {name} 说话。",
      // @patient
      nameSelf: "Nura 该怎么称呼您？",
      // @patient
      nameOther: "Nura 应该怎么称呼 {name}？",
      // @patient phrase
      nameLabel: "Nura 用的名字",
      // @patient
      languageSelf: "您想听哪种语言？",
      // @patient
      languageOther: "{name} 想听哪种语言？",
      // @patient
      bornSelf: "您是哪年出生的？",
      // @patient
      bornOther: "{name} 是哪年出生的？",
      // @patient phrase
      decade: "{decade} 年代",
      // @patient
      doctorSelf: "您最常看哪位医生？",
      // @patient
      doctorOther: "{name} 最常看哪位医生？",
      // @patient phrase
      doctorLabel: "医生的名字",
      // @patient
      doctorHint: "Nura 每次都会用这个名字。",
      // @patient
      breakfastSelf: "您一般几点吃早餐？",
      // @patient
      breakfastOther: "{name} 一般几点吃早餐？",
      // @patient
      breakfastHint: "Nura 把早上的药跟早餐连在一起。",
      // @patient phrase
      times: {
        "06:00": "早上 6 点",
        "06:30": "早上 6 点半",
        "07:00": "早上 7 点",
        "07:30": "早上 7 点半",
        "08:00": "早上 8 点",
        "08:30": "早上 8 点半",
        "09:00": "早上 9 点",
        "10:00": "早上 10 点",
      },
      // @patient
      switchSelf: {
        large_text: "字大一点对您有帮助吗？",
        high_contrast: "字深一点，您会看得更清楚吗？",
        voice_on: "要Nura把内容读给您听吗？",
        big_targets: "按钮大一点对您有帮助吗？",
        one_thing_per_screen: "要Nura一次只显示一件事吗？",
        read_back: "要Nura把它的理解说给您听吗？",
        repeat_prompts: "要Nura再提醒您一次吗？",
      },
      // @patient
      switchOther: {
        large_text: "字大一点对{name}有帮助吗？",
        high_contrast: "字深一点，{name}会看得更清楚吗？",
        voice_on: "要Nura把内容读给{name}听吗？",
        big_targets: "按钮大一点对{name}有帮助吗？",
        one_thing_per_screen: "要Nura给{name}一次只显示一件事吗？",
        read_back: "要Nura把它的理解说给{name}听吗？",
        repeat_prompts: "要Nura再提醒{name}一次吗？",
      },
      // @patient
      densitySelf: "Nura一次要给您看多少？",
      // @patient
      densityOther: "Nura一次要给{name}看多少？",
      // @patient phrase
      densitySimple: "少一点，简单一点",
      // @patient phrase
      densityDetailed: "全部都看",
      // @patient phrase
      yes: "是",
      // @patient phrase
      no: "不是",
    },
    cloud: {
      // @patient headline
      titleSelf: "您的健康有哪些方面？",
      // @patient headline
      titleOther: "{name} 的健康有哪些方面？",
      // @patient
      lead: "有的就点一下。",
      // @patient
      lead2: "Nura 会接着显示常常一起出现的。",
      // @patient
      lead3: "Nura 只用这个来知道该看哪里。",
      // @patient
      noted: "Nura 记下了。",
      // @patient
      removed: "Nura 拿掉了。",
      // @patient phrase
      more: "显示更多",
      // @patient phrase
      fewer: "显示少一些",
      // @patient phrase
      done: "就这些了",
      // @patient
      term: "医生叫它 {term}。",
    },
    asks: {
      // @patient
      lead: "请点最合适的一个。",
    },
    readBack: {
      // @patient headline
      title: "这是 Nura 的理解",
      // @patient
      lead: "请说这对不对。",
      // @patient
      lineOf: "这是第 {n} 条，共 {total} 条。",
      // @patient phrase
      yes: "对，没错",
      // @patient phrase
      no: "不对",
      // @patient
      agreed: "Nura 会记住这一条。",
      // @patient
      disputed: "Nura 不会用这一条。",
      // @patient
      nothing: "您什么都没有点。",
      // @patient
      nothingFine: "这没关系。",
      // @patient
      nothingSub: "您的文件可以补上这些。",
    },
    records: {
      // @patient headline
      titleSelf: "现在，您的文件",
      // @patient headline
      titleOther: "现在，{name} 的文件",
      // @patient phrase
      photo: "拍一张照片",
      // @patient phrase
      file: "改为选一个文件",
      // @patient phrase
      allPapers: "我的文件就这些",
      // @patient phrase
      allDone: "今天就到这里",
      // @patient
      looking: "Nura 正在看您的文件。",
      // @patient headline
      reviewTitle: "Nura 看到的内容",
      // @patient
      reviewLead: "请对着文件看每一行。",
      // @patient
      reviewLead2: "不对的地方请改一改。",
      // @patient
      sure: "这一条 Nura 有把握。",
      // @patient
      check: "请看一看这一条。",
      // @patient phrase
      changeLabel: "文件上写的",
      // @patient
      notANumber: "请输入文件上的数字。",
      // @patient
      cannotChange: "这一条如果不对，就不要它。",
      // @patient phrase
      leaveOut: "不要这一条",
      // @patient phrase
      keepIn: "留下这一条",
      // @patient
      leftOut: "Nura 不会用这一条。",
      // @patient phrase
      looksRight: "看起来没错",
      // @patient
      saved: "Nura 记下来了。",
      // @patient headline
      learnedTitle: "Nura 知道了什么",
      // @patient
      kindLabReport: "这是一份验血报告。",
      // @patient
      kindMedicineLabel: "这是一张药盒标签。",
      // @patient
      kindDischargeLetter: "这是一封出院信。",
      // @patient
      kindClinicSlip: "这是一张预约卡。",
      // @patient
      kindHandwritten: "这是一张医生手写的单子。",
      // @patient
      kindInsuranceLetter: "这是一封保险信。",
      // @patient
      kindDeviceScreen: "这是一台机器的屏幕。",
      // @patient
      unreadable: "这一条 Nura 看不清。",
      // @patient
      typeIt: "请输入文件上写的。",
      // @patient
      kindUnknown: "Nura 看不懂这一页。",
      // @patient
      unknownHint: "请把纸放平，在亮的地方再拍一次。",
      // @patient
      dated: "这份文件的日期是 {date}。",
      // @patient
      highRisk: "这种药 Nura 会格外小心。",
      // @patient
      fromPhoto: "来自您在 {date} 加的照片。",
      // @patient phrase
      otherLine: "文件上的另一行",
    },
    questions: {
      // @patient headline
      titleSelf: "您的文件带出几个问题",
      // @patient headline
      titleOther: "{name} 的文件带出几个问题",
      // @patient
      lead: "想问医生的就留下。",
      // @patient phrase
      keep: "留下这个",
      // @patient phrase
      notThis: "不要这个",
      // @patient
      kept: "Nura 会把这个留到看医生的时候。",
      // @patient
      dropped: "Nura 不会用这一条。",
      // @patient
      none: "您的文件没有带出问题。",
    },
    invite: {
      // @patient headline
      title: "谁可以看您的文件？",
      // @patient
      lead: "Nura 只会让这一个人看。",
      // @patient phrase
      nameLabel: "他们的名字",
      // @patient phrase
      phoneLabel: "他们的手机号码",
      // @patient phrase
      relationshipLabel: "他们是您的什么人",
      // @patient
      partsLead: "他们可以看的，每一样点一下。",
      // @patient phrase
      parts: {
        medicines: "您的药",
        visits: "您看医生的记事",
        readings: "您的血压本子和血糖数字",
        records: "您的文件",
      },
      // @patient phrase
      seeWords: "看这些话",
      // @patient
      wordsLead: "请读一读这些话。",
      // @patient phrase
      agree: "我同意，让他们看",
      // @patient
      done: "他们现在可以看这些了。",
    },
    plan: {
      // @patient headline
      title: "Nura 准备好了",
      // @patient
      lead: "您看到的一切都是从这里来的。",
      // @patient
      cadence1: "Nura 每天最多只问一件事。",
      // @patient
      cadence2: "点“以后”，Nura 过几天再问一次。",
      // @patient phrase
      missing: "还没有",
      // @patient
      onDay: "Nura 会在 {date} 问这件事。",
      // @patient phrase
      later: "以后",
      // @patient
      laterSaid: "Nura 过几天会再问一次。",
      // @patient
      moreOne: "之后还有 1 件。",
      // @patient
      more: "之后还有 {count} 件。",
      // @patient
      nothing: "现在什么都不缺。",
      // @patient phrase
      open: "打开 Nura",
    },
    // @patient phrase
    fields: {
      lipid_panel: {
        total_cholesterol: "总胆固醇",
        hdl: "好的胆固醇",
        ldl: "坏的胆固醇",
        triglycerides: "血里的油脂",
        vldl: "另一个血脂数字",
        tc_hdl_ratio: "胆固醇的比例",
        non_hdl_cholesterol: "去掉好胆固醇后的胆固醇",
      },
      device: { kind: "这台机器" },
      blood_pressure: { systolic: "上面的数字", diastolic: "下面的数字" },
      heart_rate: { pulse: "心跳" },
      reading: { taken_at: "什么时候量的" },
      visit: { doctor: "医生", next_visit: "下次看医生" },
      discharge: {
        admitted_on: "什么时候住院",
        discharged_on: "什么时候回家",
        reason: "为什么住院",
        weight_at_discharge: "回家时的体重",
      },
      blood_sugar: { glucose: "血糖数字" },
      lab_report: { lab: "验血的地方" },
      person: { birth_year: "出生年份", sex: "男或女" },
      medicine: {
        name: "这种药",
        strength: "药有多强",
        dose: "怎么吃",
        frequency: "多久吃一次",
        quantity: "给了多少",
        dispensed_at: "什么时候给的",
        prescriber: "哪位医生开的",
      },
    },
  },
  // The Record (W5): the screens' own lines. Every card's words are the backend's.
  record: {
    // @patient headline
    title: "您的文件",
    // @patient headline
    titleOther: "{name}的文件",
    // @patient headline
    medicines: "您的药",
    // @patient headline
    papers: "等您确认的文件",
    // @patient headline
    routine: "您的一天",
    // @patient headline
    timeline: "您的看诊",
    // @patient headline
    trends: "您的验血",
    // @patient headline
    providers: "您的医生和诊所",
    // @patient headline
    documents: "给家人的文件",
    // @patient headline
    changes: "有什么变化",
    // @patient phrase
    back: "回到您的文件",
    // @patient
    sureYes: "您已经确认了这一条。",
    // @patient
    sureRead: "Nura 看得很清楚。",
    // @patient
    disputed: "有人说这一条不对。",
    // @patient
    twice: "这个药在您的清单上有两次。",
    // @patient phrase
    aboutIt: "关于这个药",
    // @patient phrase
    add: "加一个药",
    // @patient headline
    storyPurpose: "这个药是做什么的",
    // @patient headline
    storyHow: "怎么吃",
    // @patient headline
    storyWatch: "要注意什么",
    // @patient headline
    storyAvoid: "要避开什么",
    // @patient headline
    storyForgot: "如果忘了吃",
    // @patient headline
    storyAsk: "要问医生的",
    // @patient
    addLead: "先拍一张标签的照片。",
    // @patient
    addLead2: "然后看看 Nura 读到了什么。",
    // @patient phrase
    nameLabel: "标签上的名字",
    // @patient phrase
    strengthLabel: "药的强度",
    // @patient phrase
    howLabel: "怎么吃",
    // @patient
    howHint: "照标签上写的打。",
    // @patient phrase
    countLabel: "盒子里有多少",
    // @patient phrase
    doctorLabel: "医生的名字",
    // @patient phrase
    checkIt: "检查一下",
    // @patient
    outcomeNew: "这是您清单上的新药。",
    // @patient
    outcomeRefill: "这是您清单上已有的药，又多了一些。",
    // @patient
    outcomeChange: "这张标签上的分量不一样。",
    // @patient headline
    flaggedTitle: "加之前",
    // @patient
    flaggedNone: "Nura 在您的清单上没有找到和它相冲的药。",
    // @patient
    severity: {
      major: "这一点很重要。",
      moderate: "这一点要注意。",
      minor: "这一点稍微注意。",
    },
    // @patient phrase
    pair: "{one}和{two}",
    // @patient phrase
    addIt: "加到我的清单上",
    // @patient
    added: "Nura 已经加到您的清单上了。",
    // @patient headline
    moreTitle: "家里还有",
    // @patient
    moreLead: "您在家里又找到了多少？",
    // @patient phrase
    moreLabel: "又找到多少",
    // @patient phrase
    moreYes: "对，加上去",
    // @patient
    papersNone: "没有等您确认的文件。",
    // @patient
    paperFrom: "这是{date}收到的。",
    // @patient phrase
    paperOpen: "看这份文件",
    // @patient phrase
    older: "看以前的看诊",
    // @patient
    papersWith: "有{count}份文件和它在一起。",
    // @patient
    paperWith: "有一份文件和它在一起。",
    // @patient
    nothingWith: "还没有东西和它在一起。",
    // @patient
    factsWith: "Nura 从中记下了{count}件事。",
    // @patient
    factWith: "Nura 从中记下了一件事。",
    // @patient
    since: "从{date}开始。",
    // @patient
    ended: "在{date}结束。",
    // @patient phrase
    seeIllness: "看这次生病",
    // @patient phrase
    seeDoctor: "看这位医生",
    // @patient
    endOfList: "Nura 就只有这些。",
    // @patient
    status: {
      planned: "这次看诊已安排。",
      confirmed: "这次看诊已约好。",
      attended: "您去了这次看诊。",
      not_attended: "您没有去这次看诊。",
      cancelled: "这次看诊取消了。",
    },
    // @patient headline
    illnessPapers: "这次生病的文件",
    // @patient headline
    illnessVisits: "生病期间的看诊",
    // @patient headline
    illnessMoments: "记下了什么",
    // @patient phrase
    momentOn: "{date}的{what}",
    // @patient
    photoOn: "这是{date}的一张照片。",
    // @patient
    letterOn: "这是{date}的一封信。",
    // @patient
    paperOn: "这是{date}的一份文件。",
    // @patient phrase
    putWith: "把文件放在这次生病里",
    // @patient phrase
    putThis: "把这份文件放进去",
    // @patient
    putAsk: "把这份文件放在这次生病里吗？",
    // @patient phrase
    putYes: "对，放进去",
    // @patient
    putDone: "这份文件现在在这次生病里了。",
    // @patient
    nothingToPut: "每份文件都已经在里面了。",
    // @patient phrase
    kind: {
      doctor: "医生",
      clinic: "诊所",
      hospital: "医院",
      pharmacy: "药房",
      lab: "验血的地方",
      other: "其他地方",
    },
    // @patient
    visitsMany: "Nura 这里有{count}次看诊。",
    // @patient
    visitsOne: "Nura 这里有一次看诊。",
    // @patient
    lastVisit: "上次看诊是{date}。",
    // @patient
    nextVisit: "下次看诊是{date}。",
    // @patient phrase
    where: "在哪里",
    // @patient phrase
    phone: "电话号码",
    // @patient headline
    medicinesFrom: "这里开的药",
    // @patient headline
    notesTitle: "关于这个地方的笔记",
    // @patient
    notesOnly: "只有主人和负责的家人能看这些笔记。",
    // @patient phrase
    noteLabel: "一条关于这个地方的笔记",
    // @patient phrase
    noteSave: "保存笔记",
    // @patient
    noteSaved: "Nura 保存了您的笔记。",
    // @patient
    writtenOn: "这是{date}写的。",
    // @patient headline
    waiting: "还在等",
    // @patient
    trendsLead: "选一个检查，看它的变化。",
    // @patient phrase
    analytes: {
      total_cholesterol: "您的胆固醇",
      ldl: "您的坏胆固醇",
      hdl: "您的好胆固醇",
      triglycerides: "您的血脂",
      hba1c: "您的血糖检查",
      creatinine: "您的肾指数",
      egfr: "您的肾过滤",
      potassium: "您身体的盐",
      haemoglobin: "您的血色素",
      tsh: "您的甲状腺检查",
    },
    // @patient phrase
    resultOn: "{date}的结果是{value} {unit}",
    // @patient
    rangeUnder: "范围是{upper}以下。",
    // @patient
    rangeOver: "范围是{lower}以上。",
    // @patient
    rangeBetween: "范围是{lower}到{upper}。",
    // @patient
    noRange: "Nura 没有这一项的范围。",
    // @patient
    labRange: "这个范围印在您的验血单上。",
    // @patient
    guideRange: "这个范围来自适合您年龄的指南。",
    // @patient phrase
    anchors: {
      wake: "起床的时候",
      breakfast: "早餐",
      lunch: "午餐",
      dinner: "晚餐",
      bed: "睡觉的时候",
    },
    // @patient phrase
    readings: {
      blood_pressure: "血压",
      blood_sugar: "血糖",
      weight: "体重",
    },
    // @patient phrase
    walk: "散步",
    // @patient
    notSet: "还没有人设定您的一天。",
    // @patient phrase
    setDay: "设定这一天",
    // @patient phrase
    timeLabel: "几点",
    // @patient phrase
    morningCard: "“今天”页面什么时候来",
    // @patient phrase
    walkAfter: "之后散步",
    // @patient phrase
    checkDay: "检查这一天",
    // @patient
    dayAsk: "这一天是这样吗？",
    // @patient phrase
    dayYes: "对，设定这一天",
    // @patient
    daySaved: "Nura 记下了这一天。",
    // @patient headline
    tableMoment: "什么时候",
    // @patient headline
    tableTime: "时间",
    // @patient headline
    tableMedicines: "药",
    // @patient headline
    tableReadings: "要量什么",
    // @patient
    documentsLead: "把持久授权书或医生的信放在这里。",
    // @patient phrase
    tags: {
      lpa: "持久授权书",
      medical_letter: "医生的信",
      consent_form: "签了名的同意书",
    },
    // @patient
    noDocuments: "Nura 还没有这类文件。",
    // @patient
    keptOn: "Nura 在{date}保存了这个。",
    // @patient
    backsConsent: "一份分享的同意书靠它。",
    // @patient
    backsStewardship: "照顾这些文件靠它。",
    // @patient
    chooseKind: "这是哪一种文件？",
    // @patient
    documentAdded: "Nura 保存了这份文件。",
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
    CardsStillOpen: "还有一份文件在等您同意。",
    NotAtThisStep: "这一步要晚一点才到。",
    BiographyClosed: "这次的设置已经完成了。",
    PaperAlreadyAdded: "那份文件已经和其他文件在一起了。",
    NotTheirsToSetUp: "只有主人或他的家人可以设置这个。",
    NotADecade: "请从列表里选一个年代。",
    NotALanguage: "Nura还不会说那种语言。",
    NoPlan: "Nura现在还没有要请您做的事。",
    NotPlainEnough: "请用简单的话写这个问题。",
    HolderNeedsAName: "请输入您要让他看的那个人的名字。",
    NotAPdf: "Nura 看不懂那个文件。",
    PdfTooLarge: "那个文件太大了，Nura 打不开。",
    UnreadableField: "请输入 Nura 看不清的那一行。",
    NotEveryFieldDecided: "请先看过每一行。",
    NotADecision: "Nura 不明白那个回答。",
    NoSuchReviewField: "那一行已经不在卡上了。",
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
    NotAConsultRecording: "Nura不能保存这段录音。",
    ConsultTooLong: "这段录音对Nura来说太长了。",
    NoSuchRecording: "这段录音已经不在这里了。",
    NotAClip: "Nura找不到录音的这一部分。",
    OnlyTheFamilyHears: "只有本人和他让进来的家人可以听。",
    NotTheirsToChangeVisits: "您可以看这些预约，但不能改。",
    NotAChief: ["只有本人可以做这件事。", "负责这些文件的家人也可以。"],
    NotOnThisVisit: "Nura不能把这次开车的事交给这个人。",
    NoteNamesHealth: "Nura 不能保存写了药名或病名的笔记。",
    NotAPlaceNote: "请写一句简短的话，关于这个地方。",
    NotTheirsToSet: "您可以看这一天，但不能改。",
    NotARoutine: "时间要按一天的顺序排。",
    NoSuchAnalyte: "Nura 不认识这个检查。",
    NobodyToAsk: ["家人名单上没有人可以请。", "请先把一个人加到家人名单上。"],
    NotACount: "请用数字打有多少。",
    NotADocument: "Nura 可以保存一封信或者一页纸的照片。",
    DocumentTooLarge: "这份文件太大了，Nura 放不下。",
    AlreadyHangsThere: "这份文件已经在那里了。",
    EpisodeAlreadyClosed: "这次生病已经结束了。",
    NoSuchEpisode: "这次生病已经不在这里了。",
    NoSuchProvider: "这位医生不在您的名单上。",
    StaleState: ["Nura 还在更新。", "请再试一次。"],
    NotIdentified: "Nura 找不到这个药。",
    DoseNotRead: "请照标签打怎么吃。",
    NotADose: "Nura 看不懂怎么吃。",
  },
} satisfies Strings;
