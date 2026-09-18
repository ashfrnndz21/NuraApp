import type { Strings } from "./types";

/** Malay: a first translation awaiting a native speaker's pass, like the backend's. */
export const ms = {
  // @patient headline
  appName: "Nura",
  demo: {
    // @patient headline
    banner: "Demo — bukan untuk maklumat kesihatan sebenar",
    // @patient headline
    bannerShort: "Demo. Jangan letak maklumat kesihatan sebenar.",
    // @patient
    lines: ["Ini ialah demo.", "Jangan masukkan maklumat kesihatan sebenar.", "Semua di sini dipadam setiap malam."],
  },
  tabs: {
    // @patient headline
    today: "Hari Ini",
    // @patient headline
    record: "Surat",
    // @patient headline
    me: "Saya",
    // @patient headline
    family: "Keluarga",
    // @patient headline
    home: "Utama",
    // @patient headline
    medicines: "Ubat",
    // @patient headline
    records: "Surat",
    // @patient headline
    visits: "Lawatan",
    // @patient headline
    timeline: "Surat",
    // @patient headline
    plan: "Rancangan",
    // @patient headline
    health: "Kesihatan",
    // @patient headline
    connect: "Hubungi",
    // @patient headline
    services: "Perkhidmatan",
    // @patient headline
    profile: "Profil",
  },
  shell: {
    // @patient phrase
    askNura: "Tanya Nura soalan",
    // @patient phrase
    askAbout: "Tanya tentang {name}",
    // @patient phrase
    voice: "Cakap",
    // @patient
    voiceSaid1: "Tekan gambar mikrofon kecil di tepi huruf.",
    // @patient
    voiceSaid2: "Kemudian sebut soalan anda.",
    // @patient phrase
    close: "Tutup",
    // @patient phrase
    bell: "Lagi untuk anda",
    // @patient phrase
    back: "Kembali",
    // @patient phrase
    bellFeed: "Lagi untuk anda",
    // @patient phrase
    bellInsights: "Minggu anda, dilihat dengan teliti",
  },
  welcome: {
    // @patient headline
    tagline1: "Kesihatan anda, tersimpan bersama.",
    // @patient headline
    tagline2: "Keluarga anda, sentiasa dekat.",
    // @patient
    lead: "Nura menyimpan ubat dan surat anda di satu tempat.",
    // @patient headline
    remember: "Ingat",
    // @patient line
    rememberLine: "Nura ingat ubat dan surat anda.",
    // @patient headline
    share: "Kongsi",
    // @patient line
    shareLine: "Anda pilih siapa dalam keluarga boleh melihatnya.",
    // @patient headline
    prepare: "Bersedia",
    // @patient line
    prepareLine: "Nura sediakan anda sebelum jumpa doktor.",
    // @patient phrase
    start: "Mula",
    // @patient phrase
    tryAsPa: "Cuba sebagai Pa",
    // @patient phrase
    tryAsMei: "Cuba sebagai Mei",
  },
  talk: {
    // @patient phrase
    you: "Anda bertanya",
    // @patient phrase
    nura: "Nura menjawab",
    // @patient
    working: "Nura sedang mencari.",
    // @patient
    answered: "Nura ada jawapan.",
    // @patient headline
    lookedAt: "Apa yang Nura lihat",
    // @patient
    slow: "Ini mengambil masa lebih lama daripada biasa.",
    // @patient
    failed: "Nura tidak dapat menjawab sekarang.",
    // @patient phrase
    tryAgain: "Cuba lagi",
    // @patient phrase
    loading: "Nura sedang menyediakan halaman Hari Ini anda.",
  },
  hub: {
    // @patient
    howFeeling: "Apa khabar hari ini?",
    // @patient
    howFeelingOther: "Apa khabar {patient} hari ini?",
    // @patient headline
    checkTitle: "Apa yang anda rasa hari ini",
    // @patient headline
    checkTitleOther: "Apa yang {patient} rasa hari ini",
    // @patient line
    checkLine: "Beritahu Nura apa yang anda rasa hari ini.",
    // @patient phrase
    checkLineOther: "Beritahu Nura apa yang {patient} rasa hari ini",
    // @patient phrase
    checkIn: "Beritahu Nura",
    // @patient
    doTitle: "Apa yang anda mahu buat?",
    // @patient
    doTitleOther: "Apa yang perlu dibuat untuk {patient}.",
    // @patient headline
    health: "Kesihatan",
    // @patient line
    healthLine: "Buku tekanan darah dan surat anda.",
    // @patient line
    healthLineOther: "Buku tekanan darah dan surat {patient}.",
    // @patient headline
    medicines: "Ubat",
    // @patient line
    medicinesLine: "Ubat anda, dan bila hendak makan.",
    // @patient line
    medicinesLineOther: "Ubat {patient}, dan bila hendak makan.",
    // @patient headline
    connect: "Hubungi",
    // @patient line
    connectLine: "Lihat keluarga dan kawan anda.",
    // @patient line
    connectLineOther: "Lihat keluarga dan kawan {patient}.",
    // @patient headline
    activities: "Perkara untuk dibuat",
    // @patient line
    activitiesLine: "Kekal aktif.",
    // @patient headline
    care: "Perkhidmatan penjagaan",
    // @patient line
    careLine: "Bantuan di rumah.",
    // @patient line
    careLineOther: "Bantuan untuk {patient} di rumah.",
    // @patient headline
    resources: "Panduan",
    // @patient line
    resourcesLine: "Baca dan belajar.",
    // @patient headline
    report: "Tambah surat",
    // @patient line
    reportLine: "Ambil gambarnya, atau pilih yang doktor hantar kepada anda.",
    // @patient line
    reportLineOther: "Ambil gambarnya, atau pilih yang doktor {patient} hantar.",
    // @patient line
    reportNote: "Nura akan membacanya dan tunjuk apa yang dijumpainya.",
    // @patient line
    reportNoteOther: "Nura akan membacanya dan tunjuk apa yang dijumpainya.",
    // @patient line
    reportReady: "Nura tidak akan hantar ini sehingga anda kata boleh.",
    // @patient phrase
    reportReadyOther: "Nura tidak akan hantar ini untuk {patient} sehingga anda kata boleh.",
    // @patient phrase
    reportSend: "Hantar ini",
    // @patient headline
    upcoming: "Lawatan seterusnya",
    // @patient phrase
    seeAll: "Lihat semua",
    // @patient phrase
    seeAllVisits: "Lihat semua lawatan",
    // @patient
    soonLine1: "Nura belum boleh buat ini.",
    // @patient
    soonLine2: "Kami masih membuatnya.",
    // @patient phrase
    backHome: "Kembali ke halaman Hari Ini",
    // @patient phrase
    backHomeOther: "Kembali ke halaman Hari Ini {patient}",
  },
  home: {
    // @patient headline
    mostLikely: "Keadaan hari ini",
    // @patient headline
    whatChanged: "Apa yang berubah",
    // @patient headline
    nextVisit: "Lawatan seterusnya",
    // @patient phrase
    atTime: "Pada {time}.",
    // @patient headline
    buyMore: "Beli lagi",
    // @patient headline
    missing: "Belum ada dalam surat",
    // @patient
    missingSub: "Nura sudah tambah soalan ini untuk ditanya kepada {doctor} pada {date}.",
    // @patient
    missingSubDay: "Nura sudah tambah soalan ini untuk lawatan pada {date}.",
    // @patient phrase
    bpLabel: "Tekanan darah, nombor atasnya",
    // @patient headline
    fromName: "Daripada {name}",
    // @patient phrase
    showAll: "Tunjuk semua {count}",
    // @patient phrase
    showFewer: "Tunjuk kurang",
    // @patient
    bpLast: "Kali terakhir ukur tekanan darah, nombor atasnya {number}.",
  },
  activity: {
    // @patient headline
    title: "Perkara untuk dibuat",
    // @patient headline
    weekTitle: "Minggu ini",
    // @patient phrase
    stepsLabel: "Langkah hari ini",
    // @patient phrase
    stepsSave: "Simpan",
    // @patient phrase
    waterLabel: "Cawan air hari ini",
    // @patient phrase
    waterSave: "Simpan",
    // @patient phrase
    waterSkip: "Tiada air hari ini",
    // @patient
    saved: "Nura sudah tulis.",
    // @patient headline
    mealsTitle: "Makanan anda hari ini",
    // @patient headline
    mealsTitleOther: "Makanan {patient} hari ini",
    // @patient phrase
    meal: { breakfast: "Sarapan", lunch: "Makan tengah hari", dinner: "Makan malam", snack: "Snek" },
    // @patient phrase
    skipMeal: "Tidak makan ini",
    // @patient
    skipped: "Anda tidak makan ini.",
    // @patient
    skippedOther: "{patient} tidak makan ini.",
  },
  places: {
    // @patient headline
    visitsOwn: "Lawatan anda",
    // @patient headline
    visitsOwnOther: "Lawatan {patient}",
    // @patient headline
    visitsOther: "Lawatan {name}",
    // @patient
    visitsNoneOther: "Nura belum catat apa-apa lawatan untuk {name}.",
    // @patient headline
    planTitle: "Rancangan untuk lawatan seterusnya",
    // @patient
    planLead: "Semua yang perlu untuk lawatan seterusnya ada di sini.",
    // @patient headline
    careTitle: "Perkhidmatan penjagaan",
    // @patient
    careNoneOwn: "Nura tiada perkhidmatan penjagaan tempatan untuk anda buat masa ini.",
    // @patient
    careNoneOther: "Nura tiada perkhidmatan penjagaan tempatan untuk {name} buat masa ini.",
    // @patient headline
    nearYouOwn: "Berhampiran anda",
    // @patient headline
    nearYouOther: "Berhampiran {name}",
    // @patient
    nearYouArea: "Nura tahu kawasan anda ialah {area}.",
    // @patient
    nearYouAreaOther: "Nura tahu kawasan {name} ialah {area}.",
    // @patient headline
    guidesTitle: "Panduan",
  },
  homeCare: {
    // @patient headline
    title: "Bantuan di rumah",
    // @patient phrase
    nursing: "Jururawat di rumah",
    // @patient phrase
    nursingLine: "Jururawat datang kepada anda",
    // @patient phrase
    physio: "Fisioterapi",
    // @patient phrase
    physioLine: "Kekal bergerak dengan baik",
    // @patient phrase
    meals: "Makanan",
    // @patient phrase
    mealsLine: "Dihantar kepada anda",
    // @patient phrase
    transport: "Pengangkutan",
    // @patient phrase
    transportLine: "Ke temu janji anda",
    // @patient phrase
    near: "Berhampiran anda",
    // @patient phrase
    nearOther: "Berhampiran {name}",
    // @patient
    none: "Nura tiada apa-apa berhampiran anda untuk ini lagi.",
    // @patient
    noneOther: "Nura tiada apa-apa berhampiran {name} untuk ini lagi.",
  },
  navigation: {
    // @patient phrase
    draftAction: "Tulis draf mesej",
    // @patient headline
    sheetTitle: "Draf mesej anda",
    // @patient phrase
    copy: "Salin",
    // @patient
    copied: "Sudah disalin, sedia untuk ditampal di tempat anda mahu hantar.",
    // @patient phrase
    sendBySms: "Hantar melalui mesej teks",
    // @patient phrase
    sendByWhatsApp: "Hantar melalui WhatsApp",
    // @patient
    copyOnly: "Tiada nombor untuk tempat ini, jadi salin mesej ini dan hantar sendiri.",
    // @patient
    loading: "Nura sedang menulis mesej.",
    // @patient
    error: "Nura tidak dapat menulis mesej buat masa ini.",
  },
  health: {
    // @patient headline
    title: "Kesihatan anda",
    // @patient headline
    titleOther: "Kesihatan {name}",
    // @patient headline
    thisWeek: "Minggu ini",
    // @patient headline
    readingsTitle: "Buku tekanan darah dan nombor gula",
    // @patient
    readingsWithheld: "Kunci ini tidak meliputi buku tekanan darah {name}.",
    // @patient
    readingsNone: "Belum ada apa-apa dicatat.",
    // @patient phrase
    bloodPressure: "Tekanan darah",
    // @patient phrase
    bloodSugar: "Gula dalam darah",
    // @patient phrase
    readingSource: "Daripada buku tekanan darah anda, {date}",
    // @patient phrase
    readingSourceOther: "Daripada buku tekanan darah {name}, {date}",
    // @patient phrase
    metricSource: "Daripada apa yang anda tulis, {date}",
    // @patient phrase
    metricSourceOther: "Daripada apa yang {name} tulis, {date}",
    // @patient phrase
    asOf: "Setakat {date}",
    // @patient headline
    dayTitle: "Hari anda",
    // @patient headline
    dayTitleOther: "Hari {name}",
    // @patient
    mealNotHad: "Anda tidak makan ini.",
    // @patient
    mealNotHadOther: "{name} tidak makan ini.",
    // @patient headline
    comingUpTitle: "Akan datang",
    // @patient phrase
    addReading: "Tulis tekanan darah",
  },
  insights: {
    // @patient headline
    cardTitle: "Minggu anda, dilihat dengan teliti",
    // @patient headline
    cardTitleOther: "Minggu {name}, dilihat dengan teliti",
    // @patient
    cardNone: "Nura belum melihat minggu anda.",
    // @patient
    cardNoneOther: "Nura belum melihat minggu {name}.",
    // @patient phrase
    cardLastLooked: "Nura melihat ini pada {date}",
    // @patient phrase
    generate: "Jana sekarang",
    // @patient headline
    screenTitle: "Minggu anda",
    // @patient headline
    screenTitleOther: "Minggu {name}",
    // @patient
    working: "Nura sedang melihat minggu ini.",
    // @patient phrase
    weekOf: "Minggu bermula {date}",
    sectionTitles: {
      // @patient headline
      what_changed: "Apa yang berubah",
      // @patient headline
      worth_a_look: "Patut dilihat",
      // @patient headline
      medicines_and_supplements: "Ubat dan suplemen",
      // @patient headline
      what_you_pay: "Apa yang anda bayar",
      // @patient headline
      screenings_due: "Saringan yang perlu dibuat",
      // @patient headline
      questions_for_the_doctor: "Soalan untuk doktor",
    },
    // @patient
    sectionWithheld: "Kunci ini tidak meliputi bahagian minggu {name} ini.",
    // @patient
    sectionEmpty: "Tiada apa untuk ditandakan minggu ini.",
    // @patient phrase
    why: "Sebab",
    // @patient phrase
    sure: "Pasti",
    // @patient phrase
    likely: "Berkemungkinan",
    // @patient phrase
    worthALook: "Patut dilihat",
    // @patient phrase
    askThis: "Tanya {who} soalan ini",
    // @patient
    asked: "Nura menyimpan soalan ini untuk lawatan anda.",
    // @patient
    noVisit: "Belum ada lawatan ditempah untuk bawa soalan ini.",
  },
  signIn: {
    // @patient headline
    title: "Daftar masuk",
    // @patient
    phoneLead: "Taip nombor telefon anda.",
    // @patient
    phoneHint: "Mulakan dengan kod negara anda.",
    // @patient
    nameLead: "Nura patut panggil anda apa?",
    // @patient phrase
    phoneLabel: "Nombor telefon anda",
    // @patient phrase
    nameLabel: "Nama anda",
    // @patient phrase
    sendCode: "Hantar kod kepada saya",
    // @patient phrase
    useEmail: "Daftar masuk dengan emel pula",
    // @patient phrase
    usePhone: "Daftar masuk dengan nombor telefon pula",
    // @patient
    codeLead: "Nura sudah hantar kod ke telefon anda.",
    // @patient
    codeHint: "Taip 6 angka daripada mesej itu.",
    // @patient
    codeWorks: "Kod ini boleh digunakan selama 10 minit.",
    // @patient phrase
    codeLabel: "Kod itu",
    // @patient phrase
    signInButton: "Daftar masuk",
    // @patient
    emailLead: "Taip alamat emel anda.",
    // @patient phrase
    emailLabel: "Emel anda",
    // @patient phrase
    sendLink: "Hantar pautan kepada saya",
    // @patient
    linkLead: "Nura sudah hantar pautan ke emel anda.",
    // @patient
    linkHint: "Taip kod daripada emel itu di sini.",
    // @patient phrase
    linkLabel: "Kod daripada emel",
    // @patient
    never: "Nura tidak akan menelefon anda untuk meminta kod ini.",
    // @patient phrase
    back: "Kembali",
  },
  doors: {
    // @patient headline
    title: "Ini untuk siapa?",
    // @patient phrase
    forMe: "Ini untuk saya",
    // @patient
    forMeLine: "Nura akan menyimpan surat-surat anda sendiri.",
    // @patient phrase
    forSomeone: "Ini untuk orang lain",
    // @patient
    forSomeoneLine: "Anda akan menjaga surat-surat mereka untuk mereka.",
    // @patient phrase
    invited: "Seseorang membenarkan saya masuk",
    // @patient
    invitedLine: "{name} berkongsi surat-surat dengan anda.",
    // @patient phrase
    waiting: "Ada surat-surat menunggu anda",
    // @patient
    waitingLine: "{name} menyediakannya untuk anda.",
    // @patient phrase
    lookAgain: "Cuba lihat lagi",
  },
  consent: {
    // @patient headline
    title: "Sebelum kita mula",
    // @patient
    lead: "Sila baca kata-kata ini.",
    // @patient phrase
    agree: "Saya setuju",
    // @patient phrase
    language: "Bahasa anda",
  },
  claim: {
    // @patient headline
    title: "Surat-surat ini milik anda",
    // @patient
    setUpBy: "{name}, {relationship}, menyediakan ini untuk anda.",
    // @patient
    keepsSeeing: "{name} akan terus melihat bahagian surat-surat anda ini:",
    // @patient phrase
    mine: "Ya, ini milik saya",
  },
  forSomeone: {
    // @patient headline
    title: "Anda menyediakan ini untuk siapa?",
    // @patient
    lead: "Taip nama dan nombor telefon mereka.",
    // @patient phrase
    theirName: "Nama mereka",
    // @patient phrase
    theirPhone: "Nombor telefon mereka",
    // @patient phrase
    relationshipLabel: "Siapa anda kepada mereka",
    // @patient phrase
    relationships: {
      daughter: "Anak perempuan mereka",
      son: "Anak lelaki mereka",
      spouse: "Suami atau isteri mereka",
      sibling: "Adik-beradik mereka",
      grandchild: "Cucu mereka",
      other_family: "Ahli keluarga mereka yang lain",
      helper: "Pembantu mereka",
      friend: "Kawan mereka",
      neighbour: "Jiran mereka",
      other: "Orang lain",
    },
    // @patient phrase
    pickContact: "Pilih daripada kenalan saya",
    // @patient
    asked: "Mereka minta anda buat ini.",
    // @patient phrase
    create: "Sediakan",
  },
  switcher: {
    // @patient headline
    title: "Surat-surat siapa?",
    // @patient phrase
    own: "Surat-surat anda sendiri",
    // @patient
    roleOwner: "Ini surat-surat anda sendiri.",
    // @patient
    roleChief: "Anda menjaga surat-surat ini.",
    // @patient
    roleCaregiver: "Anda boleh melihat sebahagian surat-surat ini.",
    // @patient
    roleSteward: "Anda menyediakan surat-surat ini untuk mereka.",
    // @patient
    roleOther: "Anda boleh melihat surat-surat ini.",
    // @patient phrase
    openOwn: "Surat-surat anda sendiri. Tekan untuk lihat surat orang lain.",
    // @patient phrase
    openOther: "Surat-surat {name}. Tekan untuk lihat surat orang lain.",
    // @patient
    onlyThese: "Ini sahaja surat-surat yang Nura ada untuk anda.",
    // @patient
    cannotLook: "Nura tidak dapat mencari surat lain sekarang.",
  },
  today: {
    // @patient headline
    now: "Sekarang",
    // @patient headline
    forYou: "Untuk anda hari ini",
    // @patient headline
    greetingMorning: "Selamat pagi, {name}.",
    // @patient headline
    greetingAfternoon: "Selamat tengah hari, {name}.",
    // @patient headline
    greetingEvening: "Selamat petang, {name}.",
    // @patient phrase
    taken: "Sudah ambil",
    // @patient
    tookMorning: "Anda sudah ambil ubat pagi ini.",
    // @patient
    tookAfternoon: "Anda sudah ambil ubat tengah hari tadi.",
    // @patient
    tookEvening: "Anda sudah ambil ubat petang ini.",
    // @patient
    tookNight: "Anda sudah ambil ubat malam ini.",
    // @patient
    allTaken: "Anda sudah ambil semua ubat untuk hari ini.",
    // @patient
    allTakenSub: "Tidak ada lagi yang perlu diambil hari ini.",
    // @patient
    nothingNow: "Tiada apa-apa untuk diambil sekarang.",
    // @patient
    noMedicines: "Nura belum ada ubat untuk anda.",
    // @patient
    noMedicinesSub: "Keluarga anda boleh menambahnya daripada label ubat.",
    // @patient phrase
    hear: "Dengar",
    // @patient headline
    readingTitle: "Tekanan darah anda",
    // @patient headline
    readingTitleOther: "Tekanan darah {patient}",
    // @patient
    readingLead: "Tulis nombor pagi ini.",
    // @patient
    readingLeadEvening: "Tulis nombor malam ini.",
    // @patient phrase
    aTablet: "Ubat anda",
    // @patient headline
    earlierTitle: "Dari awal hari ini",
    // @patient phrase
    readingButton: "Tulis",
    // @patient
    stateStable: "Hari anda tenang.",
    // @patient
    stateStableOther: "Keadaan {patient} stabil hari ini.",
    // @patient
    stateWatchOther: "Nura sedang memerhatikan satu perkara untuk {patient}.",
    // @patient
    callFamilyOther: "Telefon ahli keluarga yang lain sekarang.",
    // @patient
    offlineSubOther: "Ini halaman Hari Ini {patient} dari awal tadi.",
    // @patient
    asOfOther: "Nura kali terakhir membaca surat {patient} pada {date} jam {time}.",
    // @patient
    cannotReachOther: "Nura tidak dapat membuka surat {patient} sekarang.",
    // @patient
    emergencySoonOther: "Nura akan simpan kad kecemasan {patient} di sini.",
    // @patient headline
    todayListOther: "Ubat {patient} untuk hari ini",
    // @patient
    fromTodayOther: "Ini daripada halaman Hari Ini {patient}.",
    // @patient
    tookMorningOther: "{patient} sudah ambil pagi tadi.",
    // @patient
    allTakenOther: "{patient} sudah ambil semua ubat untuk hari ini.",
    // @patient
    stateWatch: "Nura sedang memerhatikan satu perkara untuk anda.",
    // @patient
    stateWatchSub: "Ia bukan sesuatu yang perlu dirisaukan hari ini.",
    // @patient
    stateAct: "Ada satu perkara untuk dibuat hari ini.",
    // @patient
    stateActSub: "Ia kad pertama di halaman ini.",
    // @patient
    staleState: "Ini daripada awal hari ini.",
    // @patient action
    callChief: "Telefon {name} sekarang.",
    // @patient action
    callFamily: "Telefon keluarga anda sekarang.",
    // @patient
    proud: "Anda sudah ambil ubat anda pada {count} hari.",
    // @patient
    proudOne: "Anda sudah ambil ubat anda pada 1 hari.",
    // @patient
    proudNone: "Bila anda tekan Sudah ambil, nombor ini jadi 1.",
    // @patient
    proudSub: "Nombor ini hanya naik.",
    // @patient headline
    supplyTitle: "Ubat anda",
    // @patient headline
    todayList: "Ubat anda untuk hari ini",
    // @patient
    offline: "Nura tidak dapat sambungan internet sekarang.",
    // @patient
    offlineSub: "Ini halaman Hari Ini anda daripada sebelum ini.",
    // @patient
    asOf: "Nura terakhir membaca surat-surat anda pada {date}, pukul {time}.",
    // @patient
    cannotReach: "Nura tidak dapat capai surat-surat anda sekarang.",
    // @patient headline
    emergencyTitle: "Kad kecemasan",
    // @patient
    emergencySoon: "Nura akan menyimpan kad kecemasan anda di sini.",
    // @patient
    homeScreen1: "Anda boleh tambah Nura ke skrin utama anda.",
    // @patient
    homeScreen2: "Tekan Kongsi di bawah skrin.",
    // @patient
    homeScreen3: "Kemudian tekan Tambah ke Skrin Utama.",
    // @patient
    fromToday: "Ini daripada halaman Hari Ini anda.",
    // @patient
    fromState: "Nura mengira ini pada {date}.",
    // @patient
    fromDays: "Nura mengira hari anda ambil ubat anda.",
    // @patient phrase
    emergencyOpen: "Kad kecemasan anda",
    // @patient phrase
    emergencyOpenOther: "Kad kecemasan {patient}",
  },
  feed: {
    // @patient headline
    title: "Lagi untuk anda",
    // @patient
    empty: "Tiada apa-apa yang baru hari ini.",
    // @patient phrase
    emptyAction: "Kembali ke Hari Ini",
    // @patient phrase
    open: "Lihat lagi untuk anda",
    // @patient headline
    story: "Kisah anda",
    // @patient headline
    learning: "Dalam kata-kata mudah",
    // @patient headline
    didYouKnow: "Tahukah anda",
    // @patient phrase
    ask: "Tanya",
    // @patient phrase
    family: "Keluarga",
    // @patient phrase
    notForMe: "Bukan untuk saya",
    // @patient phrase
    keepGoing: "Teruskan",
    // @patient phrase
    toTablets: "Lihat ubat anda",
    // @patient
    declined: "Nura sudah tulis bahawa ini bukan untuk anda.",
    // @patient
    declinedToday: "Anda tidak akan lihat kad seperti ini lagi hari ini.",
    // @patient
    shared: "Keluarga anda boleh lihat kad ini sekarang.",
    // @patient phrase
    fromPublisher: "Daripada {publisher}",
    // @patient phrase
    whyLink: "Kenapa saya nampak ini?",
    // @patient headline
    whyTitle: "Kenapa saya nampak ini?",
    // @patient
    cannotShare: "Nura belum boleh hantar kad ini kepada keluarga anda.",
    // @patient
    quiet: "Nura senyap pada waktu malam.",
    // @patient
    quietSub: "Kad anda kembali pada waktu pagi.",
    // @patient
    nothingMore: "Tiada apa-apa lagi untuk anda sekarang.",
    // @patient
    offlineSub: "Ini kad anda dari awal hari ini.",
    // @patient headline
    askTitle: "Tanya Nura",
    // @patient phrase
    askAbout: "Tentang kad ini",
    // @patient phrase
    askLabel: "Soalan anda",
    // @patient
    askLead: "Taip, atau tekan mikrofon pada papan kekunci.",
    // @patient
    sourcePapers: "Ini datang dari surat-surat anda.",
    // @patient
    sourceMedicines: "Ini datang dari senarai ubat anda.",
    // @patient
    sourceVisits: "Ini datang dari lawatan anda ke doktor.",
    // @patient
    askWithheld: "Sebahagian surat-surat ini tidak dibuka untuk anda.",
    // @patient
    askThinking: "Nura sedang mencari.",
    // @patient
    lookingForToday: "Nura sedang mencari bacaan hari ini.",
    // @patient
    askAnswered: "Nura sudah menjawab.",
    // @patient phrase
    askLookedAt: "Apa yang Nura lihat: {parts}",
    // @patient phrase
    back: "Kembali ke kad anda",
    // @patient
    statusHeld: "Nura tidak tunjuk kad ini kepada {name}.",
    // @patient
    statusSent: "Kad ini ada di halaman yang {name} lihat.",
    // @patient
    statusOpened: "{name} sudah buka kad ini.",
    // @patient
    statusPlayed: "{name} sudah dengar kad ini.",
    // @patient
    statusDismissed: "{name} tekan Bukan untuk saya pada kad ini.",
    // @patient phrase
    play: "Main",
    // @patient phrase
    watchAgain: "Tonton semula",
    // @patient phrase
    watchWhole: "Tonton seluruh video di {publisher}",
    // @patient phrase
    askOrSearch: "Tanya atau cari",
    // @patient phrase
    filterLabel: "Cari di mana",
    // @patient phrase
    filterRecords: "Surat anda",
    // @patient phrase
    filterWeb: "Web",
    // @patient phrase
    filterProviders: "Doktor dan klinik",
    // @patient phrase
    filterVideos: "Video",
    // @patient phrase
    search: "Cari",
    // @patient phrase
    readPage: "Baca halaman di {publisher}",
    // @patient
    foundNothing: "Nura tidak jumpa apa-apa untuk ini.",
    // @patient phrase
    nextVisit: "Lawatan anda yang seterusnya pada {date}.",
  },
  reading: {
    // @patient headline
    title: "Tekanan darah anda",
    // @patient headline
    titleOther: "Tekanan darah {patient}",
    // @patient
    lead: "Taip 2 nombor daripada mesin itu.",
    // @patient phrase
    top: "Nombor atas",
    // @patient phrase
    bottom: "Nombor bawah",
    // @patient phrase
    save: "Simpan",
    // @patient
    saved: "Nura sudah tulis.",
    // @patient phrase
    cancel: "Bukan sekarang",
    // @patient phrase
    photo: "Ambil gambar mesin",
    // @patient
    photoLead: "Atau ambil gambar skrin mesin.",
  },
  me: {
    // @patient headline
    title: "Saya",
    // @patient
    signedInAs: "Anda daftar masuk sebagai {name}.",
    // @patient phrase
    language: "Bahasa anda",
    // @patient phrase
    en: "English",
    // @patient phrase
    ms: "Bahasa Melayu",
    // @patient phrase
    zh: "中文",
    // @patient phrase
    look: "Rupa Nura",
    // @patient phrase
    patient: "Besar dan ringkas",
    // @patient phrase
    caregiver: "Kecil, lebih banyak dalam satu halaman",
    // @patient phrase
    lookAuto: "Biar Nura pilih",
    // @patient phrase
    switchProfile: "Lihat surat-surat orang lain",
    // @patient phrase
    setUp: "Sediakan Nura",
    // @patient phrase
    signOut: "Daftar keluar",
    // @patient phrase
    remindersGet: "Dapatkan peringatan di telefon ini",
    // @patient phrase
    emergencyPrint: "Cetak",
    // @patient
    remindersOn: "Peringatan sudah dihidupkan untuk telefon ini.",
    // @patient phrase
    remindersStop: "Hentikan peringatan di telefon ini",
    // @patient
    remindersDenied1: "Telefon ini tidak benarkan peringatan.",
    // @patient
    remindersDenied2: "Anda boleh ubah dalam tetapan telefon.",
    // @patient headline
    areaTitle: "Tempat anda tinggal",
    // @patient
    areaLead: "Nura guna bandar anda hanya untuk denggi, jerebu atau cuaca panas dekat anda.",
    // @patient
    areaNone: "Nura tidak tahu bandar anda.",
    // @patient
    areaIs: "Nura tahu bandar anda ialah {area}.",
    // @patient
    areaAsk: "Adakah anda tinggal di {area}?",
    // @patient phrase
    areaYes: "Ya, saya tinggal di situ",
    // @patient phrase
    areaNo: "Tidak",
    // @patient phrase
    areaChange: "Pilih bandar anda",
    // @patient phrase
    areaClear: "Jangan simpan bandar saya",
    // @patient
    areaWho: "Orang yang menjaga surat-surat anda boleh nampak bandar anda.",
    // @patient headline
    ramadanTitle: "Bulan puasa",
    // @patient
    ramadanLead: "Jika anda berpuasa pada bulan puasa, Nura boleh bantu anda merancang.",
    // @patient
    ramadanWho: "Orang yang menjaga surat-surat anda juga akan nampak ini.",
    // @patient phrase
    ramadanYes: "Ya, beritahu saya sebelum bulan puasa",
    // @patient
    ramadanOn: "Nura akan beritahu anda sebelum bulan puasa.",
    // @patient phrase
    ramadanStop: "Berhenti beritahu saya",
    // @patient headline
    whatNuraUsesTitle: "Apa yang Nura guna",
    // @patient
    whatNuraUsesLead: "Pilih apa yang Nura boleh guna untuk cadangkan bacaan dan video untuk anda.",
    // @patient
    whatNuraUsesLeadOther: "Pilih apa yang Nura boleh guna untuk cadangkan bacaan dan video untuk {patient}.",
    // @patient phrase
    whatNuraUsesOn: "Buka",
    // @patient phrase
    whatNuraUsesOff: "Tutup",
    // @patient
    whatNuraUsesReadOnly: "Hanya {name} atau ketua keluarga boleh ubah ini.",
    whatNuraUsesFamilies: {
      // @patient phrase
      food: "Apa yang anda makan",
      // @patient phrase
      sleep: "Tidur anda",
      // @patient phrase
      steps: "Langkah anda",
      // @patient phrase
      water: "Air anda",
      // @patient phrase
      search_topics: "Apa yang anda tanya",
    },
    whatNuraUsesFamiliesOther: {
      // @patient phrase
      food: "Apa yang {patient} makan",
      // @patient phrase
      sleep: "Tidur {patient}",
      // @patient phrase
      steps: "Langkah {patient}",
      // @patient phrase
      water: "Air {patient}",
      // @patient phrase
      search_topics: "Apa yang {patient} tanya",
    },
    // @patient phrase
    insurance: "Insurans",
  },
  insurance: {
    // @patient headline
    title: "Insurans anda",
    // @patient headline
    titleOther: "Insurans {patient}",
    // @patient
    none: "Nura tiada surat insurans untuk anda lagi.",
    // @patient
    noneOther: "Nura tiada surat insurans untuk {patient} lagi.",
    type: {
      // @patient phrase
      hospital: "Perlindungan hospital",
      // @patient phrase
      outpatient: "Perlindungan pesakit luar",
      // @patient phrase
      critical_illness: "Perlindungan penyakit kritikal",
      // @patient phrase
      government_scheme: "Skim kerajaan",
    },
    status: {
      // @patient phrase
      active: "Aktif",
      // @patient phrase
      lapsed: "Luput",
      // @patient phrase
      cancelled: "Dibatalkan",
    },
    // @patient
    covers: "Ia melindungi {value}.",
    // @patient
    renews: "Ia diperbaharui pada {date}.",
    // @patient
    premiumDue: "Bayaran seterusnya perlu dibayar pada {date}.",
    // @patient
    reference: "Nombor polisinya {reference}.",
  },
  // The visit day (E05-03, E05-04): the logistics card, the recording, the clips.
  visit: {
    // @patient headline
    title: "Lawatan anda",
    // @patient phrase
    open: "Lihat lawatan anda yang seterusnya",
    // @patient phrase
    openOther: "Lihat lawatan {patient} yang seterusnya",
    // @patient
    none: "Nura tiada lawatan yang ditulis untuk anda.",
    // @patient
    fromVisit: "Ini datang dari lawatan anda ke doktor.",
    // @patient
    onDuty: "Hari itu giliran {name}.",
    // @patient phrase
    driveYes: "Ya, {name} akan hantar",
    // @patient phrase
    start: "Mula merakam",
    // @patient
    keepOpen: "Biarkan halaman ini terbuka semasa Nura mendengar.",
    // @patient
    consentLead: "Nura perlukan persetujuan anda sebelum mendengar.",
    // @patient phrase
    saidYes: "{doctor} kata boleh",
    // @patient phrase
    saidNo: "{doctor} kata tidak",
    // @patient
    listening: "Nura sedang mendengar.",
    // @patient phrase
    stop: "Berhenti",
    // @patient
    saving: "Nura sedang menyimpan rakaman.",
    // @patient
    saved: "Nura sudah menyimpan rakaman.",
    // @patient
    notHeard: "Nura tidak dapat mendengar kata-katanya.",
    // @patient
    notHeardSub: "Anda boleh dengar semula dalam surat-surat anda.",
    // @patient
    cardLater: "Nura belum dapat membuat kad itu.",
    // @patient
    stoppedAway: "Nura berhenti mendengar apabila anda meninggalkan halaman ini.",
    // @patient phrase
    keepHeard: "Simpan apa yang Nura dengar",
    // @patient phrase
    hearClip: "Dengar apa yang {doctor} kata",
    // @patient headline
    byHandTitle: "Tulis apa yang {doctor} kata",
    // @patient phrase
    byHandLabel: "Apa yang {doctor} kata",
    // @patient phrase
    byHandSave: "Simpan nota",
    // @patient
    noMic: "Nura tidak boleh guna mikrofon telefon ini.",
    // @patient
    noMicSub: "Anda boleh tulis nota dengan tangan.",
    // @patient
    noConnection: "Telefon tiada sambungan sekarang.",
    // @patient
    sendLater: "Nura hantar rakaman itu apabila sambungan kembali.",
    // @patient
    keepOpenToSend: "Biarkan halaman ini terbuka sehingga itu.",
  },
  // Tekanan semasa telefon tidak dapat capai Nura (E00-08).
  held: {
    // @patient
    held: "Nura akan menghantar apa yang anda tekan apabila internet kembali.",
    // @patient
    tapped: "Anda tekan ini pada {time}.",
    // @patient
    sent: "Nura sudah menghantar apa yang anda tekan.",
  },
  // Kad kecemasan di telefon (E00-08).
  emergency: {
    // @patient
    asOf: "Nura terakhir membaca kad ini pada {date}.",
    // @patient
    none: "Kad kecemasan anda belum ada di telefon ini.",
    // @patient
    noneSub: "Buka kad ini sekali lagi nanti, semasa internet ada.",
    // @patient phrase
    callChief: "Telefon {name}",
    // @patient phrase
    callAmbulance: "Telefon ambulans di {number}",
    // @patient phrase
    print: "Cetak kad ini",
  },
  // Surat daripada gambar (E18-01).
  papers: {
    // @patient phrase
    open: "Tambah surat daripada gambar anda",
    // @patient phrase
    chooseMany: "Pilih banyak gambar",
    // @patient headline
    title: "Surat daripada gambar anda",
    // @patient
    lead: "Pilih semua gambar surat sekali gus.",
    // @patient
    lead2: "Nura tidak hantar apa-apa sehingga anda tekan Hantar.",
    // @patient phrase
    pick: "Pilih gambar",
    // @patient
    gridLead: "Tekan gambar untuk tinggalkannya.",
    // @patient phrase
    picture: "Surat {count}",
    // @patient
    tileIn: "Nura akan hantar yang ini.",
    // @patient
    tileOut: "Nura tidak akan hantar yang ini.",
    // @patient phrase
    sendOne: "Hantar 1 surat",
    // @patient phrase
    send: "Hantar {count} surat",
    // @patient
    sending: "Nura sedang menghantar surat {n} daripada {total}.",
    // @patient
    working: "Nura sedang membuatnya.",
    // @patient headline
    found: "Apa yang Nura jumpa",
    // @patient
    read: "Nura sudah membaca surat ini.",
    // @patient phrase
    check: "Semak surat ini",
    // @patient
    notHealth: "Ini bukan surat kesihatan.",
    // @patient
    notSent: "Internet tiada tadi, jadi yang ini belum dihantar.",
    // @patient phrase
    sendRest: "Hantar yang belum dihantar",
    // @patient
    nothingKept: "Nura tidak simpan gambar di telefon ini.",
    // @patient phrase
    backToday: "Kembali ke Hari Ini",
  },
  // Pemain yang satu (E15-07).
  player: {
    // @patient phrase
    play: "Mainkan",
    // @patient phrase
    pause: "Berhenti sekejap",
    // @patient phrase
    speed: "Kelajuan Nura bercakap",
    // @patient phrase
    slower: "Lebih perlahan",
    // @patient phrase
    usual: "Kelajuan biasa",
    // @patient phrase
    faster: "Lebih laju",
    // @patient phrase
    nextPart: "Bahagian seterusnya",
    // @patient phrase
    hearStory: "Dengar tentang {name}",
  },
  day: {
    // @patient headline
    topThree: "3 perkara untuk hari ini",
    // @patient phrase
    notWell: "Saya rasa tidak sihat",
    // @patient headline
    notWellTitle: "Beritahu Nura apa yang anda rasa",
    // @patient headline
    notWellTitleOther: "Beritahu Nura apa yang {patient} rasa",
    // @patient
    notWellLead: "Sebut atau taip dengan kata-kata anda sendiri.",
    // @patient phrase
    wordsLabel: "Apa yang anda rasa",
    // @patient phrase
    wordsLabelOther: "Apa yang {patient} rasa",
    // @patient phrase
    send: "Beritahu Nura",
    // @patient phrase
    sayIt: "Sebut dengan kuat",
    // @patient phrase
    stopAndSend: "Berhenti dan hantar",
    // @patient
    sending: "Nura sedang menghantar ini sekarang.",
    // @patient headline
    whatToDo: "Apa perlu dibuat sekarang",
    // @patient phrase
    backToday: "Kembali ke Hari Ini",
    // @patient phrase
    symptomsOpen: "Catat apa yang anda rasa",
    // @patient phrase
    notWellOther: "{patient} rasa tidak sihat",
    // @patient phrase
    symptomsOpenOther: "Tulis bagaimana perasaan {patient}",
    // @patient headline
    symptomsTitleSelf: "Bagaimana perasaan anda",
    // @patient headline
    symptomsTitleOther: "Bagaimana perasaan {name}",
    // @patient
    symptomsLead: "Sebut apa yang anda rasa, teruk mana dan sejak bila.",
    // @patient
    symptomsLeadOther: "Sebut apa yang {patient} rasa, teruk mana dan sejak bila.",
    // @patient phrase
    symptomsKeep: "Simpan ini",
    // @patient phrase
    sendAgain: "Hantar sekali lagi",
    // @patient
    symptomsSaved: "Nura sudah tulis ini.",
    // @patient phrase
    nudgeOk: "OK",
    // @patient phrase
    nudgeWentWell: "Semuanya baik",
    // @patient phrase
    nudgeNotToday: "Bukan hari ini",
    // @patient phrase
    briefOpen: "Baca sebelum lawatan anda",
    // @patient phrase
    briefOpenOther: "Baca sebelum lawatan {patient}",
    // @patient headline
    briefTitle: "Sebelum lawatan anda",
    // @patient phrase
    questionsOpen: "Soalan anda untuk doktor",
    // @patient phrase
    questionsOpenOther: "Soalan untuk doktor {patient}",
    // @patient headline
    questionsTitle: "Soalan untuk lawatan anda",
    // @patient phrase
    questionLabel: "Soalan anda",
    // @patient phrase
    questionAdd: "Simpan soalan ini",
    // @patient
    questionCheck: "Adakah ini yang anda mahu tanya?",
    // @patient phrase
    questionYes: "Ya, simpan",
    // @patient phrase
    questionRemove: "Buang soalan ini",
    // @patient
    questionRemoveCheck: "Buang soalan ini daripada senarai anda?",
    // @patient phrase
    questionRemoveYes: "Ya, buang",
    // @patient
    questionKept: "Nura sudah simpan soalan anda.",
    // @patient
    questionRemoved: "Nura sudah buang soalan itu daripada senarai anda.",
    // @patient
    summaryLead: "Semak setiap baris, kemudian kata ya.",
    // @patient phrase
    summaryLeaveOut: "Jangan simpan ini",
    // @patient
    summaryLeftOut: "Nura tidak akan simpan ini.",
    // @patient
    summaryFromNotes: "Ini daripada nota yang anda tulis.",
    // @patient phrase
    summaryYes: "Ya, simpan kad ini",
    // @patient
    summaryKept: "Nura sudah simpan apa yang {doctor} katakan.",
    // @patient
    summaryWaiting: "Kad ini menunggu jawapan ya daripada anda.",
    fallback: {
      // @patient
      youDidRight: "Bagus, anda sudah beritahu.",
      // @patient action
      notSent: "Nura tidak dapat menghantar ini kepada keluarga anda.",
      // @patient action
      call995: "Hubungi ambulans sekarang di talian 995.",
      // @patient action
      call999: "Hubungi ambulans sekarang di talian 999.",
      // @patient action
      callFamily: "Telefon keluarga anda sekarang.",
      // @patient action
      bad995: "Jika anda rasa sangat teruk, hubungi ambulans sekarang di talian 995.",
      // @patient action
      bad999: "Jika anda rasa sangat teruk, hubungi ambulans sekarang di talian 999.",
      // @patient
      closing: "Nura tidak menentukan apa masalahnya.",
    },
  },
  onboarding: {
    // @patient phrase
    next: "Seterusnya",
    // @patient phrase
    notNow: "Bukan sekarang",
    // @patient phrase
    later: "Sediakan kemudian",
    // @patient phrase
    back: "Kembali",
    // @patient
    saving: "Nura sedang menulisnya.",
    about: {
      // @patient headline
      titleSelf: "Sedikit tentang anda",
      // @patient headline
      titleOther: "Sedikit tentang {name}",
      // @patient
      leadSelf: "Ini menentukan cara Nura bercakap dengan anda.",
      // @patient
      leadOther: "Ini menentukan cara Nura bercakap dengan {name}.",
      // @patient
      nameSelf: "Nura patut panggil anda apa?",
      // @patient
      nameOther: "Nura patut panggil {name} apa?",
      // @patient phrase
      nameLabel: "Nama yang Nura guna",
      // @patient
      languageSelf: "Anda mahu dengar dalam bahasa apa?",
      // @patient
      languageOther: "{name} mahu dengar dalam bahasa apa?",
      // @patient
      bornSelf: "Bila anda dilahirkan?",
      // @patient
      bornOther: "Bila {name} dilahirkan?",
      // @patient phrase
      decade: "Tahun {decade}-an",
      // @patient
      doctorSelf: "Doktor mana yang paling kerap anda jumpa?",
      // @patient
      doctorOther: "Doktor mana yang paling kerap {name} jumpa?",
      // @patient phrase
      doctorLabel: "Nama doktor itu",
      // @patient
      doctorHint: "Nura akan guna nama ini setiap kali.",
      // @patient
      breakfastSelf: "Pukul berapa anda biasa bersarapan?",
      // @patient
      breakfastOther: "Pukul berapa {name} biasa bersarapan?",
      // @patient
      breakfastHint: "Nura ikat ubat pagi dengan sarapan.",
      // @patient phrase
      times: {
        "06:00": "Pukul 6 pagi",
        "06:30": "Pukul 6 setengah pagi",
        "07:00": "Pukul 7 pagi",
        "07:30": "Pukul 7 setengah pagi",
        "08:00": "Pukul 8 pagi",
        "08:30": "Pukul 8 setengah pagi",
        "09:00": "Pukul 9 pagi",
        "10:00": "Pukul 10 pagi",
      },
      // @patient
      switchSelf: {
        large_text: "Adakah tulisan yang lebih besar membantu anda?",
        high_contrast: "Adakah tulisan yang lebih gelap membantu anda membaca?",
        voice_on: "Patutkah Nura membacakan sesuatu kepada anda?",
        big_targets: "Adakah butang yang lebih besar membantu anda?",
        one_thing_per_screen: "Patutkah Nura tunjuk satu perkara pada satu masa?",
        read_back: "Patutkah Nura ulang apa yang ia faham?",
        repeat_prompts: "Patutkah Nura ingatkan anda sekali lagi?",
      },
      // @patient
      switchOther: {
        large_text: "Adakah tulisan yang lebih besar membantu {name}?",
        high_contrast: "Adakah tulisan yang lebih gelap membantu {name} membaca?",
        voice_on: "Patutkah Nura membacakan sesuatu kepada {name}?",
        big_targets: "Adakah butang yang lebih besar membantu {name}?",
        one_thing_per_screen: "Patutkah Nura tunjuk {name} satu perkara pada satu masa?",
        read_back: "Patutkah Nura ulang kepada {name} apa yang ia faham?",
        repeat_prompts: "Patutkah Nura ingatkan {name} sekali lagi?",
      },
      // @patient
      densitySelf: "Berapa banyak patut Nura tunjuk kepada anda sekali gus?",
      // @patient
      densityOther: "Berapa banyak patut Nura tunjuk kepada {name} sekali gus?",
      // @patient phrase
      densitySimple: "Sedikit, dengan mudah",
      // @patient phrase
      densityDetailed: "Semuanya, dengan penuh",
      // @patient phrase
      yes: "Ya",
      // @patient phrase
      no: "Tidak",
    },
    cloud: {
      // @patient headline
      titleSelf: "Apa yang ada dalam kesihatan anda?",
      // @patient headline
      titleOther: "Apa yang ada dalam kesihatan {name}?",
      // @patient
      lead: "Tekan setiap satu yang berkenaan.",
      // @patient
      lead2: "Nura akan tunjuk apa yang selalu datang bersamanya.",
      // @patient
      lead3: "Nura guna ini hanya untuk tahu di mana hendak melihat.",
      // @patient
      noted: "Nura sudah tulis itu.",
      // @patient
      removed: "Nura sudah buang itu.",
      // @patient phrase
      more: "Tunjuk lebih banyak perkataan",
      // @patient phrase
      fewer: "Tunjuk kurang perkataan",
      // @patient phrase
      done: "Itu sahaja",
      // @patient
      term: "Doktor panggilnya {term}.",
      // @patient
      countNone: "Nura belum tulis apa-apa lagi.",
      // @patient
      count: "Nura sudah tulis {n} perkara.",
      // @patient phrase
      tellMe: "Atau beritahu saja",
      // @patient
      tellMeLead: "Cakap dengan kata-kata anda sendiri.",
      // @patient phrase
      tellMeLabel: "Dengan kata-kata anda sendiri",
      // @patient phrase
      tellMeSend: "Hantar",
      // @patient
      tellMeNothing: "Nura tidak jumpa perkataan di atas untuk itu.",
      // @patient
      tellMeNothingSub: "Cuba tekan sahaja.",
      // @patient
      tellMeSafety: "Nura tidak akan jadikan itu satu perkataan di sini.",
      // @patient
      tellMeSafetySub: "Sila beritahu seseorang yang anda percaya, atau dapatkan bantuan sekarang.",
    },
    asks: {
      // @patient
      lead: "Tekan yang paling sesuai.",
    },
    readBack: {
      // @patient headline
      title: "Ini yang Nura faham",
      // @patient
      lead: "Sila beritahu jika ini betul.",
      // @patient
      lineOf: "Ini yang ke-{n} daripada {total}.",
      // @patient phrase
      yes: "Ya, itu betul",
      // @patient phrase
      no: "Tidak, itu tidak betul",
      // @patient
      agreed: "Nura akan simpan itu.",
      // @patient
      disputed: "Nura tidak akan guna yang itu.",
      // @patient
      nothing: "Anda tidak tekan apa-apa.",
      // @patient
      nothingFine: "Itu tidak mengapa.",
      // @patient
      nothingSub: "Surat-surat anda boleh isikannya.",
    },
    records: {
      // @patient headline
      titleSelf: "Sekarang, surat-surat anda",
      // @patient headline
      titleOther: "Sekarang, surat-surat {name}",
      // @patient phrase
      photo: "Ambil gambar",
      // @patient phrase
      file: "Pilih dokumen pula",
      // @patient phrase
      allPapers: "Itu sahaja surat-surat saya",
      // @patient phrase
      allDone: "Itu sahaja untuk hari ini",
      // @patient
      looking: "Nura sedang melihat surat anda.",
      // @patient headline
      reviewTitle: "Apa yang Nura baca",
      // @patient
      reviewLead: "Semak setiap baris dengan surat itu.",
      // @patient
      reviewLead2: "Tukar apa-apa yang salah.",
      // @patient
      sure: "Nura pasti tentang yang ini.",
      // @patient
      check: "Sila semak yang ini.",
      // @patient phrase
      changeLabel: "Apa yang tertulis pada surat",
      // @patient
      notANumber: "Sila taip nombor daripada surat itu.",
      // @patient
      cannotChange: "Jika yang ini salah, tinggalkannya.",
      // @patient phrase
      leaveOut: "Tinggalkan yang ini",
      // @patient phrase
      keepIn: "Simpan yang ini",
      // @patient
      leftOut: "Nura akan tinggalkan yang ini.",
      // @patient phrase
      looksRight: "Nampak betul",
      // @patient
      saved: "Nura sudah tulis.",
      // @patient headline
      learnedTitle: "Apa yang Nura belajar",
      // @patient
      kindLabReport: "Ini ujian darah.",
      // @patient
      kindMedicineLabel: "Ini label ubat.",
      // @patient
      kindDischargeLetter: "Ini surat hospital.",
      // @patient
      kindClinicSlip: "Ini kad temu janji.",
      // @patient
      kindHandwritten: "Ini nota tulisan tangan doktor.",
      // @patient
      kindInsuranceLetter: "Ini surat insurans.",
      // @patient
      kindInsurancePolicy: "Ini polisi insurans.",
      // @patient
      kindInsuranceClaim: "Ini tuntutan insurans.",
      // @patient
      kindDeviceScreen: "Ini skrin sebuah mesin.",
      // @patient
      kindOther: "Ini surat kesihatan.",
      // @patient
      unreadable: "Nura tidak dapat membaca yang ini.",
      // @patient
      typeIt: "Sila taip apa yang tertulis pada surat itu.",
      // @patient
      fromPage: "Daripada muka surat {page} surat ini.",
      // @patient
      kindUnknown: "Nura tidak dapat membaca halaman ini.",
      // @patient
      unknownHint: "Cuba lagi dengan kertas rata, di tempat terang.",
      // @patient
      dated: "Surat ini bertarikh {date}.",
      // @patient
      highRisk: "Nura lebih berhati-hati dengan ubat ini.",
      // @patient
      fromPhoto: "Daripada gambar yang anda tambah pada {date}.",
      // @patient phrase
      otherLine: "Satu lagi baris pada surat",
    },
    questions: {
      // @patient headline
      titleSelf: "Surat-surat anda ada beberapa soalan",
      // @patient headline
      titleOther: "Surat-surat {name} ada beberapa soalan",
      // @patient
      lead: "Simpan soalan untuk ditanya kepada doktor.",
      // @patient phrase
      keep: "Simpan yang ini",
      // @patient phrase
      notThis: "Bukan yang ini",
      // @patient
      kept: "Nura akan simpan yang ini untuk lawatan.",
      // @patient
      dropped: "Nura akan tinggalkan yang ini.",
      // @patient
      none: "Surat-surat anda tidak ada soalan.",
    },
    invite: {
      // @patient headline
      title: "Siapa yang boleh melihat surat-surat anda?",
      // @patient
      lead: "Nura akan membenarkan seorang ini sahaja.",
      // @patient phrase
      nameLabel: "Nama mereka",
      // @patient phrase
      phoneLabel: "Nombor telefon mereka",
      // @patient phrase
      relationshipLabel: "Siapa mereka kepada anda",
      // @patient phrase
      relationships: {
        daughter: "Anak perempuan anda",
        son: "Anak lelaki anda",
        spouse: "Suami atau isteri anda",
        sibling: "Adik-beradik anda",
        grandchild: "Cucu anda",
        other_family: "Ahli keluarga anda yang lain",
        helper: "Pembantu anda",
        friend: "Kawan anda",
        neighbour: "Jiran anda",
        other: "Orang lain",
      },
      // @patient
      partsLead: "Tekan setiap bahagian yang boleh mereka lihat.",
      // @patient phrase
      parts: {
        medicines: "Ubat-ubat anda",
        visits: "Lawatan anda ke doktor",
        readings: "Buku tekanan darah dan nombor gula anda",
        records: "Surat-surat anda",
      },
      // @patient phrase
      seeWords: "Lihat kata-kata ini",
      // @patient
      wordsLead: "Sila baca kata-kata ini.",
      // @patient phrase
      agree: "Saya setuju, beri mereka kunci",
      // @patient
      done: "Mereka boleh melihat bahagian itu sekarang.",
    },
    plan: {
      // @patient headline
      title: "Nura sudah sedia",
      // @patient
      lead: "Semua yang anda lihat dibina daripada ini.",
      // @patient
      cadence1: "Nura akan minta satu perkara sehari, tidak lebih.",
      // @patient
      cadence2: "Tekan Nanti dan Nura akan tanya sekali lagi.",
      // @patient
      missing: "Nura belum ada yang ini.",
      // @patient
      onDay: "Nura akan minta ini pada {date}.",
      // @patient phrase
      later: "Nanti",
      // @patient
      laterSaid: "Nura akan tanya sekali lagi dalam beberapa hari.",
      // @patient
      moreOne: "Ada 1 lagi selepas itu.",
      // @patient
      more: "Ada {count} lagi selepas itu.",
      // @patient
      nothing: "Nura sudah ada semua yang perlu buat masa ini.",
      // @patient phrase
      open: "Buka Nura",
    },
    // @patient phrase
    fields: {
      lipid_panel: {
        total_cholesterol: "Jumlah kolesterol",
        hdl: "Kolesterol baik",
        ldl: "Kolesterol jahat",
        ldl_reference_range: "Julat normal kolesterol jahat",
        triglycerides: "Lemak dalam darah",
        vldl: "Satu lagi nombor lemak darah",
        tc_hdl_ratio: "Nisbah kolesterol",
        non_hdl_cholesterol: "Kolesterol tanpa bahagian baik",
      },
      full_blood_count: { hemoglobin: "Nombor kiraan darah" },
      device: { kind: "Mesin itu" },
      blood_pressure: { systolic: "Nombor atas", diastolic: "Nombor bawah" },
      heart_rate: { pulse: "Degupan jantung" },
      reading: { taken_at: "Bila ia diambil" },
      visit: { doctor: "Doktor itu", next_visit: "Lawatan seterusnya" },
      discharge: {
        admitted_on: "Bila anda masuk",
        discharged_on: "Bila anda pulang",
        reason: "Mengapa anda di hospital",
        weight_at_discharge: "Berat anda semasa pulang",
      },
      follow_up: { date: "Bila hendak kembali" },
      hypertension: { control: "Apa yang doktor tulis tentang tekanan darah anda" },
      blood_sugar: { glucose: "Nombor gula" },
      lab_report: {
        lab: "Tempat darah diuji",
        facility: "Tempat ia diuji",
        remark: "Apa yang laporan itu kata selain nombor",
        patient_name: "Nama pada laporan",
        patient_id: "Nombor pesakit pada laporan",
        ordering_doctor: "Doktor mana yang memintanya",
      },
      person: { birth_year: "Tahun lahir", sex: "Lelaki atau perempuan" },
      medicine: {
        name: "Ubat itu",
        strength: "Berapa kuat ubat itu",
        dose: "Cara mengambilnya",
        frequency: "Berapa kerap mengambilnya",
        quantity: "Berapa banyak yang diberi",
        dispensed_at: "Bila ia diberi",
        prescriber: "Doktor mana yang menulisnya",
      },
      insurance_policy: {
        insurer: "Syarikat insurans",
        policy_number: "Nombor polisi",
        plan: "Pelan itu",
        holder: "Siapa yang dilindungi polisi ini",
        start_date: "Bila ia bermula",
        end_date: "Bila ia tamat",
      },
      insurance_claim: {
        insurer: "Syarikat insurans",
        claim_number: "Nombor tuntutan",
        status: "Status tuntutan itu",
        amount: "Jumlah wang",
        date: "Tarikh",
        for: "Untuk apa tuntutan itu",
      },
    },
  },
  // The Record (W5): the screens' own lines. Every card's words are the backend's.
  record: {
    // @patient headline
    title: "Surat anda",
    // @patient headline
    titleOther: "Surat {name}",
    // @patient headline
    medicines: "Ubat anda",
    // @patient headline
    medicinesOther: "Ubat {patient}",
    // @patient headline
    papers: "Surat yang menunggu ya anda",
    // @patient headline
    papersOther: "Surat yang menunggu ya",
    // @patient headline
    routine: "Hari anda",
    // @patient headline
    routineOther: "Hari {patient}",
    // @patient headline
    timeline: "Lawatan anda",
    // @patient headline
    timelineOther: "Lawatan {patient}",
    // @patient headline
    trends: "Ujian darah anda",
    // @patient headline
    trendsOther: "Ujian darah {patient}",
    // @patient headline
    providers: "Doktor dan klinik anda",
    // @patient headline
    providersOther: "Doktor dan klinik {patient}",
    // @patient headline
    changes: "Apa yang berubah",
    // @patient headline
    ledger: "Wang insurans anda",
    // @patient headline
    ledgerOther: "Wang insurans {patient}",
    // @patient
    ledgerWithheld: "Ini disimpan untuk anda sahaja.",
    // @patient
    ledgerWithheldOther: "Ini disimpan untuk {patient} sahaja.",
    // @patient phrase
    back: "Kembali ke surat anda",
    // @patient phrase
    backOther: "Kembali ke surat {patient}",
    // @patient
    sureYes: "Anda sudah kata ya untuk ini.",
    // @patient
    sureYesOther: "{patient} sudah kata ya untuk ini.",
    // @patient
    sureRead: "Nura membaca ini dengan jelas.",
    // @patient
    disputed: "Ada yang kata ini tidak betul.",
    // @patient
    matchByNameOnly: ["Nura jumpa ubat ini melalui nama pada label.", "Label tidak beritahu berapa kuat ubat ini."],
    // @patient
    twice: "Ubat ini ada dua kali dalam senarai anda.",
    // @patient
    twiceOther: "Ubat ini ada dua kali dalam senarai {patient}.",
    // @patient phrase
    aboutIt: "Tentang ubat ini",
    // @patient phrase
    add: "Tambah ubat",
    // @patient headline
    storyPurpose: "Untuk apa",
    // @patient headline
    storyHow: "Cara mengambilnya",
    // @patient headline
    storyWatch: "Apa yang perlu diperhatikan",
    // @patient headline
    storyAvoid: "Apa yang perlu dielakkan",
    // @patient headline
    storyForgot: "Jika anda terlupa",
    // @patient headline
    storyAsk: "Untuk ditanya kepada doktor anda",
    // @patient phrase
    hearParts: {
      purpose: "Dengar untuk apa ubat ini",
      how_to_take: "Dengar cara mengambilnya",
      watch_out: "Dengar apa yang perlu diperhatikan",
      avoid: "Dengar apa yang perlu dielakkan",
      if_forgotten: "Dengar apa yang perlu dibuat jika anda terlupa",
      doctor_question: "Dengar apa yang perlu ditanya kepada doktor anda",
    },
    storyAskOther: "Untuk ditanya kepada doktor {patient}",
    // @patient
    addLead: "Ambil gambar label dahulu.",
    // @patient
    addLead2: "Kemudian semak apa yang Nura baca.",
    // @patient phrase
    nameLabel: "Nama pada label",
    // @patient phrase
    strengthLabel: "Berapa kuat ubat ini",
    // @patient phrase
    howLabel: "Cara mengambilnya",
    // @patient
    howHint: "Taip seperti yang tertulis pada label.",
    // @patient phrase
    countLabel: "Berapa banyak dalam kotak",
    // @patient phrase
    doctorLabel: "Nama doktor",
    // @patient phrase
    checkIt: "Semak",
    // @patient
    outcomeNew: "Ini ubat baharu untuk senarai anda.",
    // @patient
    outcomeRefill: "Ini tambahan untuk ubat yang anda ambil sekarang.",
    outcomeNewOther: "Ini ubat baru untuk senarai {patient}.",
    // @patient
    outcomeRefillOther: "Ini tambahan ubat yang sudah ada dalam senarai {patient}.",
    // @patient
    outcomeChange: "Label ini ada jumlah yang lain.",
    // @patient headline
    flaggedTitle: "Sebelum anda tambah",
    // @patient
    flaggedNone: "Nura tidak jumpa ubat dalam senarai anda yang tidak sesuai dengannya.",
    // @patient
    flaggedNoneOther: "Nura tidak jumpa apa-apa dalam senarai {patient} yang tidak sesuai dengannya.",
    // @patient
    severity: {
      major: "Yang ini sangat penting.",
      moderate: "Yang ini penting.",
      minor: "Yang ini sedikit penting.",
    },
    // @patient phrase
    pair: "{one} dan {two}",
    // @patient phrase
    addIt: "Tambah ke senarai saya",
    // @patient
    added: "Nura sudah tambah ke senarai anda.",
    // @patient
    addedOther: "Nura sudah tambah ke senarai {patient}.",
    // @patient headline
    moreTitle: "Ada lagi di rumah",
    // @patient
    moreLead: "Berapa banyak lagi yang anda jumpa di rumah?",
    // @patient phrase
    moreLabel: "Berapa banyak lagi",
    // @patient phrase
    moreYes: "Ya, tambah",
    // @patient
    morePhoto: "Ambil gambar label ubat dahulu.",
    // @patient
    morePhotoWhy: "Untuk ubat ini, Nura perlu lihat label ubat.",
    // @patient
    morePhotoKept: "Nura sudah ada gambar label ubat itu.",
    // @patient phrase
    orderYes: "Ya, minta keluarga pesan",
    // @patient phrase
    orderNo: "Bukan sekarang",
    // @patient
    papersNone: "Tiada surat yang menunggu ya anda.",
    // @patient
    papersNoneOther: "Tiada surat yang menunggu ya.",
    // @patient
    paperFrom: "Ini sampai pada {date}.",
    // @patient phrase
    paperOpen: "Lihat surat ini",
    // @patient phrase
    older: "Tunjuk lawatan lama",
    // @patient
    papersWith: "{count} surat ada bersamanya.",
    // @patient
    paperWith: "Satu surat ada bersamanya.",
    // @patient
    nothingWith: "Belum ada apa-apa bersamanya.",
    // @patient
    factsWith: "Nura menulis {count} perkara daripadanya.",
    // @patient
    factWith: "Nura menulis satu perkara daripadanya.",
    // @patient
    since: "Ia bermula pada {date}.",
    // @patient
    ended: "Ia berakhir pada {date}.",
    // @patient phrase
    seeIllness: "Lihat sakit ini",
    // @patient phrase
    seeDoctor: "Lihat doktor ini",
    // @patient
    endOfList: "Itu sahaja yang Nura ada.",
    // @patient
    status: {
      planned: "Lawatan ini dirancang.",
      confirmed: "Lawatan ini sudah ditetapkan.",
      attended: "Anda sudah pergi ke lawatan ini.",
      not_attended: "Anda tidak pergi ke lawatan ini.",
      cancelled: "Lawatan ini dibatalkan.",
    },
    // @patient headline
    illnessPapers: "Surat untuk sakit ini",
    // @patient headline
    illnessVisits: "Lawatan semasa sakit ini",
    // @patient headline
    illnessMoments: "Apa yang ditulis",
    // @patient
    moments: {
      reading: "Satu nombor baharu ditulis pada {date}.",
      dose_taken: "Satu ubat diambil pada {date}.",
      symptom: "Apa yang anda rasa ditulis pada {date}.",
      discharge: "Anda pulang dari hospital pada {date}.",
      visit: "Ada lawatan pada {date}.",
      other: "Sesuatu ditulis pada {date}.",
    },
    // @patient
    photoOn: "Ini gambar dari {date}.",
    // @patient
    letterOn: "Ini surat dari {date}.",
    // @patient
    paperOn: "Ini kertas dari {date}.",
    // @patient phrase
    putWith: "Letak surat bersama sakit ini",
    // @patient phrase
    putThis: "Letak surat ini bersamanya",
    // @patient
    putAsk: "Letak surat ini bersama sakit ini?",
    // @patient phrase
    putYes: "Ya, letak di situ",
    // @patient
    putDone: "Surat itu kini bersama sakit ini.",
    // @patient
    nothingToPut: "Semua surat sudah ada bersamanya.",
    // @patient phrase
    kind: {
      doctor: "Doktor",
      clinic: "Klinik",
      hospital: "Hospital",
      pharmacy: "Farmasi",
      lab: "Tempat ujian darah",
      other: "Tempat lain",
    },
    // @patient
    visitsMany: "Nura ada {count} lawatan di sini.",
    // @patient
    visitsOne: "Nura ada satu lawatan di sini.",
    // @patient
    lastVisit: "Lawatan terakhir pada {date}.",
    // @patient
    nextVisit: "Lawatan seterusnya pada {date}.",
    // @patient phrase
    where: "Di mana",
    // @patient phrase
    phone: "Nombor telefon",
    // @patient headline
    medicinesFrom: "Ubat dari sini",
    // @patient headline
    notesTitle: "Nota tentang tempat ini",
    // @patient
    notesOnly: "Hanya anda dan orang yang menjaga surat-surat ini boleh baca nota ini.",
    // @patient phrase
    noteLabel: "Satu nota tentang tempat ini",
    // @patient phrase
    noteSave: "Simpan nota",
    // @patient
    noteSaved: "Nura sudah simpan nota anda.",
    // @patient
    noteSavedOther: "Nura sudah simpan nota ini.",
    // @patient
    writtenOn: "Ini ditulis pada {date}.",
    // @patient headline
    waiting: "Masih menunggu",
    // @patient
    trendsLead: "Pilih satu ujian untuk melihatnya dari masa ke masa.",
    // @patient phrase
    analytes: {
      total_cholesterol: "Kolesterol anda",
      ldl: "Kolesterol jahat anda",
      hdl: "Kolesterol baik anda",
      triglycerides: "Lemak darah anda",
      hba1c: "Ujian gula anda",
      creatinine: "Nombor buah pinggang anda",
      egfr: "Penapis buah pinggang anda",
      potassium: "Garam badan anda",
      haemoglobin: "Kiraan darah anda",
      tsh: "Ujian tiroid anda",
    },
    // Ayat penuh, bukan frasa: berdiri sendiri sebagai satu perenggan (Day.tsx), yang dibaca
    // sebagai satu unit lengkap oleh pembaca skrin (#166 review).
    // @patient phrase
    analytesOther: {
      total_cholesterol: "Kolesterol {patient}",
      ldl: "Kolesterol jahat {patient}",
      hdl: "Kolesterol baik {patient}",
      triglycerides: "Lemak darah {patient}",
      hba1c: "Ujian gula {patient}",
      creatinine: "Nombor buah pinggang {patient}",
      egfr: "Penapis buah pinggang {patient}",
      potassium: "Garam badan {patient}",
      haemoglobin: "Kiraan darah {patient}",
      tsh: "Ujian tiroid {patient}",
    },
    // @patient
    resultOn: "Bacaannya {value} pada {date}.",
    // Her density only (the caregiver's table of results): the unit stays with the number.
    // Never shown to him, so not a patient string; `resultOn` is his.
    resultOnUnit: "{value} {unit} pada {date}",
    // @patient
    rangeUnder: "Bagi kebanyakan orang, nombor ini di bawah {upper}.",
    // @patient
    rangeOver: "Bagi kebanyakan orang, nombor ini di atas {lower}.",
    // @patient
    rangeBetween: "Bagi kebanyakan orang, nombor ini {lower} hingga {upper}.",
    // @patient
    noRange: "Nura tiada nombor biasa untuk yang ini.",
    // @patient
    labRange: "Nombor biasa itu tercetak pada ujian darah anda.",
    // @patient
    guideRange: "Nombor biasa itu dari panduan untuk umur anda.",
    // @patient
    noRangeBecause: {
      needs_age: "Nura perlukan umur anda untuk cari nombor biasa.",
      needs_sex: "Nura perlu tahu sama ada anda lelaki atau perempuan.",
      none_on_file: "Nura tiada nombor biasa untuk yang ini.",
    },
    // @patient phrase
    anchors: {
      wake: "Apabila anda bangun",
      breakfast: "Sarapan",
      lunch: "Makan tengah hari",
      dinner: "Makan malam",
      bed: "Waktu tidur",
    },
    // @patient phrase
    anchorsOther: {
      wake: "Apabila {patient} bangun",
      breakfast: "Sarapan",
      lunch: "Makan tengah hari",
      dinner: "Makan malam",
      bed: "Waktu tidur",
    },
    // @patient phrase
    readings: {
      blood_pressure: "Tekanan darah",
      blood_sugar: "Gula dalam darah",
      weight: "Berat badan",
    },
    // @patient phrase
    walk: "Berjalan kaki",
    // @patient
    notSet: "Belum ada sesiapa menetapkan hari anda.",
    // @patient
    notSetOther: "Belum ada sesiapa menetapkan hari {patient}.",
    // @patient phrase
    setDay: "Tetapkan hari anda",
    // @patient phrase
    setDayOther: "Tetapkan hari {patient}",
    // @patient phrase
    timeLabel: "Pukul berapa",
    // @patient phrase
    morningCard: "Bila halaman Hari Ini sampai",
    // @patient phrase
    walkAfter: "Berjalan kaki selepas ini",
    // @patient phrase
    checkDay: "Semak hari anda",
    // @patient
    dayAsk: "Beginikah hari anda?",
    // @patient
    dayAskOther: "Beginikah hari {patient}?",
    // @patient phrase
    dayYes: "Ya, tetapkan hari anda",
    // @patient
    daySaved: "Nura sudah tulis hari anda.",
    // @patient headline
    tableMoment: "Bila",
    // @patient headline
    tableTime: "Pukul",
    // @patient headline
    tableMedicines: "Ubat",
    // @patient headline
    tableReadings: "Apa yang perlu diperiksa",
    // @patient phrase
    ledgerTotals: "Jumlah untuk {year}",
    // @patient phrase
    ledgerClaimedLabel: "Dituntut",
    // @patient phrase
    ledgerInsurerPaidLabel: "Syarikat insurans bayar",
    // @patient phrase
    ledgerPatientPaidLabel: "Anda bayar",
    // @patient phrase
    ledgerPatientPaidLabelOther: "{patient} bayar",
    // @patient
    ledgerNone: "Belum ada tuntutan lagi.",
    // @patient phrase
    ledgerOn: "Pada {date}",
  },
  family: {
    // @patient headline
    title: "Keluarga",
    // @patient headline
    circleSelf: "Siapa boleh melihat surat-surat anda",
    // @patient headline
    circleOther: "Siapa boleh melihat surat-surat {name}",
    // @patient headline
    trailSelf: "Siapa melihat surat-surat anda",
    // @patient headline
    trailOther: "Siapa melihat surat-surat {name}",
    // @patient headline
    onlyMe: "Simpan satu bahagian untuk diri sendiri",
    // @patient
    onlyMeLead: "Tekan satu bahagian untuk menyimpannya untuk diri sendiri.",
    // @patient phrase
    onlyMeYes: "Ya, hanya saya",
    // @patient phrase
    onlyMeLift: "Benarkan mereka melihatnya semula",
    // @patient phrase
    onlyMeMarked: "Hanya anda",
    // @patient headline
    consentsSelf: "Apa yang anda setuju",
    // @patient headline
    consentsOther: "Apa yang {name} setuju",
    // @patient phrase
    stop: "Hentikan ini",
    // @patient phrase
    stopYes: "Ya, hentikan",
    // @patient phrase
    closeAccount: "Tutup akaun saya",
    // @patient phrase
    closeAccountOther: "Tutup akaun {name}",
    // @patient phrase
    closeAccountYes: "Ya, tutup akaun saya",
    // @patient phrase
    closeAccountYesOther: "Ya, tutup akaun {name}",
    // @patient phrase
    keepCopy: "Simpan salinan untuk dicetak",
    // @patient phrase
    savePage: "Simpan halaman ini",
    // @patient headline
    thread: "Mesej keluarga",
    // @patient phrase
    threadEarlier: "Tunjuk hari sebelumnya",
    // @patient phrase
    messageLabel: "Mesej anda kepada keluarga",
    // @patient phrase
    sendMessage: "Hantar kepada keluarga",
    // @patient phrase
    sendingMessage: "Menghantar kepada keluarga",
    // @patient headline
    keys: "Ubah siapa boleh melihat apa",
    // @patient headline
    newKey: "Beri seseorang kunci",
    // @patient phrase
    holderName: "Nama mereka",
    // @patient phrase
    holderPhone: "Nombor telefon mereka",
    // @patient phrase
    roleLabel: "Siapa mereka",
    // @patient phrase
    partsLabel: "Apa yang boleh mereka lihat",
    // @patient phrase
    windowLabel: "Untuk berapa lama",
    // @patient phrase
    makeKey: "Buat kunci",
    // @patient phrase
    seeWords: "Lihat kata-kata ini",
    // @patient
    wordsLead: "Sila baca kata-kata ini.",
    // @patient phrase
    agreeKey: "Saya setuju, beri mereka kunci",
    // @patient phrase
    narrow: "Kecilkan",
    // @patient phrase
    narrowYes: "Ya, kecilkan",
    // @patient phrase
    closeKey: "Tutup kunci ini",
    // @patient phrase
    closeYes: "Ya, tutup sekarang",
    // @patient phrase
    notNow: "Bukan sekarang",
    // @patient phrase
    roles: {
      chief: "Menjaga semuanya",
      caregiver: "Penjaga",
      viewer: "Hanya melihat",
      helper: "Pembantu",
      emergency: "Kecemasan sahaja",
      clinic: "Klinik",
    },
    // @patient phrase
    windows: {
      always: "Sehingga dihentikan",
      thirty_days: "30 hari",
      seventy_two_hours: "3 hari",
      one_day: "1 hari",
    },
    // @patient phrase
    parts: {
      medicines: "Ubat",
      visits: "Lawatan ke doktor",
      readings: "Buku tekanan darah dan nombor gula",
      records: "Surat-surat",
      notes: "Nota peribadi",
      money: "Surat insurans",
      emergency: "Kad kecemasan",
      family: "Senarai keluarga",
      ask: "Soalan kepada Nura",
      send: "Mesej yang Nura hantar",
    },
    // @patient headline
    roster: "Siapa bertugas, dan tugasan",
    // @patient headline
    rosterTitle: "Siapa bertugas",
    // @patient phrase
    who: "Siapa",
    // @patient phrase
    days: "Hari",
    // @patient phrase
    from: "Dari",
    // @patient phrase
    to: "Hingga",
    // @patient phrase
    onDutyNow: "Bertugas sekarang",
    // @patient phrase
    takeOff: "Keluarkan dari senarai",
    // @patient phrase
    addSlot: "Letak bertugas",
    // @patient headline
    tasksTitle: "Tugasan",
    // @patient phrase
    taskWhat: "Apa yang perlu dibuat",
    // @patient phrase
    taskDue: "Sebelum bila",
    // @patient phrase
    addTask: "Beri tugasan",
    // @patient phrase
    done: "Sudah siap",
    // @patient phrase
    doneChip: "Siap",
    // @patient phrase
    nextVisit: "Lihat lawatan seterusnya dan siapa memandu",
    // @patient headline
    messagesTitle: "Mesej untuk {name}",
    // @patient phrase
    templates: {
      pickup: "Masa ambil",
      call_you: "Masa untuk telefon",
      see_doctor: "Satu lawatan ke doktor",
      thinking_of_you: "Teringatkan anda",
      weigh_tomorrow: "Naik penimbang esok",
      drink_water: "Minum segelas air",
    },
    // @patient phrase
    ownWords: "Kata-kata saya sendiri",
    // @patient phrase
    slots: {
      who: "Siapa",
      when: "Bila",
      doctor: "Doktor mana",
      day: "Hari apa",
    },
    // @patient phrase
    memoLabel: "Satu baris setiap satu",
    // @patient phrase
    languageLabel: "Dalam bahasa apa",
    // @patient phrase
    preview: "Lihat rupanya nanti",
    // @patient phrase
    sendAt: "Hantar dari",
    // @patient phrase
    until: "Hingga",
    // @patient phrase
    channelApp: "Dalam aplikasi",
    // @patient phrase
    channelWhatsapp: "Di WhatsApp",
    // @patient phrase
    schedule: "Jadualkan",
    // @patient phrase
    states: {
      scheduled: "Menunggu dihantar",
      sent: "Sudah dihantar",
      not_sent: "Tidak dihantar pada masanya",
    },
    // @patient headline
    metrics: "Minggu ini dalam nombor",
    // @patient phrase
    weekOf: "Minggu {date}",
    // @patient phrase
    taps: "Kali ditekan",
    // @patient phrase
    fineToday: "Sihat hari ini",
    // @patient phrase
    fineShare: "Sihat hari ini, daripada 100",
    // @patient phrase
    kind: "Jenis",
    // @patient phrase
    handedOver: "Diberi",
    // @patient phrase
    accepted: "Diterima",
    // @patient phrase
    dismissed: "Diketepikan",
    // @patient phrase
    kinds: {
      anticipation: "Bersedia",
      check_in: "Bertanya khabar",
      pattern: "Satu corak",
      commitment: "Satu janji",
      recognition: "Syabas",
      presence: "Teringatkan anda",
    },
    // @patient phrase
    kindsTheirs: {
      anticipation: "Menyediakan {name}",
      check_in: "Bertanya khabar {name}",
      pattern: "Satu corak dalam hari-hari {name}",
      commitment: "Satu janji yang dibuat {name}",
      recognition: "Syabas untuk {name}",
      presence: "Teringatkan {name}",
    },
    // @patient headline
    calendar: "Lawatan daripada kalendar",
    // @patient phrase
    chooseFile: "Pilih dokumen kalendar",
    // @patient phrase
    agree: "Saya setuju",
    // @patient phrase
    bookYes: "Ya, tempah lawatan ini",
    // @patient phrase
    notThis: "Bukan yang ini",
    // @patient phrase
    ladderYes: "Saya uruskan",
    // @patient headline
    deliveries: "Apa yang Nura hantar",
    // @patient headline
    settings: "Bila dan bagaimana Nura hantar",
    // @patient phrase
    triggers: {
      morning: "Kad pagi",
      dose: "Peringatan ubat",
      reorder: "Masa beli lagi",
      doses_untapped: "Ubat belum ditekan",
      flag: "Tidak sihat",
      visit_tomorrow: "Lawatan esok",
      papers: "Surat menunggu",
      family_message: "Mesej daripada keluarga",
      first_week_prompt: "Minggu pertama",
      nudge: "Peringatan kecil",
      check_in: "Apa khabar hari ini",
      family_notice: "Apa yang Nura tulis minggu ini",
    },
    // @patient phrase
    channels: {
      app_push: "Aplikasi",
      whatsapp: "WhatsApp",
      caregiver: "Melalui penjaga",
      in_app: "Dalam aplikasi",
    },
    // @patient phrase
    outcomes: {
      sent: "Sudah dihantar",
      capped: "Ditahan: cukup untuk hari ini",
      quiet: "Ditahan: waktu senyap",
      no_channel: "Tiada cara untuk sampai kepada mereka",
      no_scope: "Kunci mereka tidak meliputinya",
      skipped: "Dilangkau pada hari yang tenang",
    },
    // @patient
    skippedBecause: {
      flagOpen: "Ditahan: sesuatu tentang {name} tidak sihat didahulukan hari ini.",
      saidToday: "Ditahan: {name} sudah beritahu keadaannya hari ini.",
      nudgeAsked: "Ditahan: Nura sudah bertanya khabar {name} hari ini.",
      questionOpen: "Ditahan: {name} masih ada soalan daripada Nura untuk dijawab.",
    },
    // @patient phrase
    rule: "Peraturan",
    // @patient phrase
    quietFrom: "Senyap dari",
    // @patient phrase
    quietUntil: "Senyap hingga",
    // @patient phrase
    skipQuietDays: "Pada hari yang tenang, langkau kad pagi",
    // @patient phrase
    cap: "Berapa kali sehari",
    // @patient phrase
    saveSettings: "Simpan tetapan ini",
    // @patient phrase
    neverHeld: "Tidak pernah ditahan",
    // @patient phrase
    everyWay: "Nura sentiasa beritahu keluarga anda tentang ini, dengan setiap cara yang boleh.",
    // @patient headline
    documents: "Surat untuk senarai keluarga",
    // @patient phrase
    tags: {
      lpa: "Surat kuasa wakil berkekalan",
      medical_letter: "Surat doktor",
      consent_form: "Borang persetujuan",
    },
    // @patient phrase
    backs: {
      consent: "Menyokong satu persetujuan",
      stewardship: "Menyokong penjagaan surat-surat",
    },
    // @patient phrase
    stillOn: "Masih berjalan",
    // @patient phrase
    stoppedChip: "Sudah dihentikan",
    // @patient phrase
    addDocument: "Tambah surat",
    // @patient phrase
    chooseDocument: "Pilih dokumen atau foto",
    // @patient phrase
    whatPaper: "Jenis surat apa",
  },
  connect: {
    // @patient headline
    familyTitle: "Keluarga anda",
    // @patient headline
    familyTitleOther: "Keluarga {patient}",
    // @patient phrase
    addPerson: "Tambah",
    // @patient phrase
    addPersonLine: "Orang baru",
    // @patient line
    noFamily: "Belum ada sesiapa yang memegang kunci kepada surat-surat anda.",
    // @patient line
    noFamilyOther: "Belum ada sesiapa yang memegang kunci kepada surat-surat {patient}.",
    // @patient headline
    nextCallTitle: "Panggilan seterusnya",
    // @patient phrase
    call: "Panggil",
    // @patient phrase
    change: "Tukar",
    // @patient line
    noCall: "Belum ada panggilan dalam kalendar anda.",
    // @patient line
    noCallOther: "Belum ada panggilan dengan {patient} dalam kalendar.",
    // @patient headline
    nearYouTitle: "Berhampiran anda",
    // @patient headline
    nearYouTitleOther: "Berhampiran {patient}",
    // @patient line
    noNearYou: "Belum ada apa-apa berhampiran anda.",
    // @patient line
    noNearYouOther: "Belum ada apa-apa berhampiran {patient}.",
    // @patient headline
    messagesTitle: "Mesej",
    // @patient line
    noMessages: "Belum ada mesej.",
    // @patient phrase
    seeAllFamily: "Lihat semua yang memegang kunci",
    // @patient phrase
    seeAllNearYou: "Lihat semua yang berhampiran",
    // @patient phrase
    seeAllMessages: "Lihat semua mesej",
    // @patient headline
    callsTitle: "Panggilan",
    // @patient phrase
    scheduleCall: "Aturkan satu panggilan",
    // @patient phrase
    cancelCallButton: "Batalkan panggilan ini",
    // @patient line
    cancelledCall: "Panggilan ini sudah dibatalkan.",
    // @patient phrase
    personLabel: "Dengan siapa",
    // @patient phrase
    whenLabel: "Bila",
    // @patient phrase
    linkLabel: "Pautan panggilan, jika ada",
    // @patient phrase
    callLabelLabel: "Nama untuk panggilan ini",
  },
  visitSuggest: {
    // @patient phrase
    followUpWhy: "Daripada surat hospital anda",
    // @patient phrase
    medicineReviewWhy: "Daripada ubat anda",
    // @patient phrase
    testComingWhy: "Daripada ujian darah anda",
    // @patient phrase
    screeningDueWhy: "Daripada surat-surat anda",
    // @patient
    rowOther: "Nura mencadangkan {name} berjumpa doktor.",
    // @patient phrase
    bookIt: "Tempahkan",
    // @patient phrase
    notNow: "Bukan sekarang",
  },
  review: {
    // @patient headline
    title: "Senarai ahli farmasi",
    // @patient phrase
    tokenLabel: "Token kakitangan",
    // @patient phrase
    open: "Buka senarai",
    // @patient headline
    statusTitle: "50 yang pertama setiap kad",
    // @patient phrase
    cardType: "Kad",
    // @patient phrase
    sampled: "Disimpan",
    // @patient phrase
    pending: "Menunggu",
    // @patient phrase
    stillToCheck: "Masih perlu disemak",
    // @patient phrase
    sourcesWaiting: "Sumber menunggu: {count}",
    // @patient headline
    queueTitle: "Menunggu keputusan",
    // @patient phrase
    showPending: "Yang menunggu sahaja",
    // @patient phrase
    showAll: "Semua",
    // @patient phrase
    approve: "Luluskan",
    // @patient phrase
    reject: "Tolak",
    // @patient phrase
    reasonLabel: "Mengapa",
    // @patient phrase
    rewrite: "Tulis semula baris",
    // @patient phrase
    headline: "Tajuk",
    // @patient phrase
    body: "Baris",
    // @patient phrase
    voice: "Baris yang dibaca",
    // @patient phrase
    why: "Mengapa kad ini",
    // @patient phrase
    saveRewrite: "Simpan sebagai cadangan",
    // @patient phrase
    decided: "Sudah diputuskan",
    // @patient phrase
    leave: "Tutup senarai",
  },
  errors: {
    // @patient
    network: "Nura tidak dapat sambungan internet sekarang.",
    // @patient phrase
    tryAgain: "Cuba lagi",
  },
  chief: {
    // @patient headline
    sentTitle: "Dihantar kepada {name} minggu ini",
    // @patient
    sentNone: "Nura tidak hantar apa-apa kepada {name} minggu ini.",
    // @patient headline
    watchingTitle: "Nura perhatikan untuk {name}",
    // @patient
    watchingNone: "Nura belum perhatikan apa-apa lagi.",
    // @patient
    sourcesNote: "Nura hanya membaca pihak berkuasa kesihatan, hospital dan persatuan doktor.",
    // @patient phrase
    onChange: "Bila ada yang baru",
    // @patient phrase
    daily: "Setiap hari",
    // @patient phrase
    weekly: "Setiap minggu",
    // @patient phrase
    beforeVisits: "Sebelum setiap lawatan",
    // @patient phrase
    once: "Sekali",
    // @patient phrase
    paused: "Dihentikan dulu",
    // @patient phrase
    pause: "Berhenti dulu",
    // @patient phrase
    resume: "Mula semula",
    // @patient phrase
    pauseWatch: "Berhenti memerhatikan ini buat masa ini",
    // @patient phrase
    add: "Perhatikan sesuatu yang baru",
    // @patient
    addLead: "Pilih apa yang Nura patut perhatikan.",
    // @patient
    added: "Nura akan perhatikan ini mulai sekarang.",
    // @patient phrase
    dengue: "Denggi",
    // @patient phrase
    haze: "Jerebu",
    // @patient phrase
    heat: "Cuaca panas",
    // @patient phrase
    festiveFood: "Makanan perayaan",
  },
  // @patient
  refusals: {
    // @patient
    FastingIsHisToSay: "Hanya pemilik boleh jawab ini.",
    // @patient
    NotAClipCard: "Kad ini tiada apa-apa untuk dimainkan.",
    // @patient
    NoExcerpt: "Nura bacakan gambar ini untuk anda.",
    // @patient
    NoClipRenderer: "Nura tidak dapat tunjuk gambar ini sekarang.",
    // @patient
    SecondsOnlyOnAPlay: "Nura tidak dapat tulis ini.",
    // @patient
    NotACadence: "Sila pilih berapa kerap daripada senarai.",
    // @patient
    NotAHazard: "Nura boleh perhatikan denggi, jerebu atau cuaca panas.",
    // @patient
    NotASeason: "Nura boleh perhatikan bulan puasa atau makanan perayaan.",
    // @patient
    NotACoarseArea: ["Sila pilih bandar anda dari senarai.", "Atau taip hanya awal poskod anda."],
    // @patient
    OnlyHeSetsHisArea: "Hanya pemilik boleh pilih bandar.",
    // @patient
    NotAFilter: "Sila pilih di mana hendak cari.",
    // @patient
    NothingToFind: "Sila taip perkataan yang anda mahu cari.",
    // @patient
    NotTheirsToManage: ["Hanya pemilik boleh buat ini.", "Orang yang menjaga surat-surat ini juga boleh."],
    default: "Nura tidak dapat buat itu sekarang.",
    NotInTheDemo: ["Demo ini hanya menerima nombor telefon ujian.", "Nombor ujian bermula dengan +65 0."],
    CardsStillOpen: "Satu surat masih menunggu persetujuan anda.",
    NotAtThisStep: "Langkah itu datang sedikit kemudian.",
    BiographyClosed: "Persediaan ini sudah selesai.",
    PaperAlreadyAdded: "Surat itu sudah bersama yang lain.",
    NotTheirsToSetUp: "Hanya pemilik atau keluarganya boleh menyediakan ini.",
    NotADecade: "Sila pilih satu dekad daripada senarai.",
    NotALanguage: "Nura belum bercakap bahasa itu.",
    NoPlan: "Nura belum ada apa-apa untuk diminta.",
    NotPlainEnough: "Sila tulis soalan itu dengan perkataan mudah.",
    HolderNeedsAName: "Sila taip nama orang yang anda benarkan.",
    NotAPdf: "Nura tidak dapat membaca dokumen itu.",
    PdfTooLarge: "Dokumen itu terlalu besar untuk Nura.",
    UnreadableField: "Sila taip baris yang Nura tidak dapat baca.",
    NotEveryFieldDecided: "Sila semak setiap baris dahulu.",
    NotADecision: "Nura tidak faham jawapan itu.",
    NoSuchReviewField: "Baris itu sudah tiada pada kad.",
    NoSession: "Sila daftar masuk semula.",
    NoOpenChallenge: "Minta kod baharu dahulu.",
    WrongCode: "Kod itu tidak betul.",
    ChallengeExpired: "Kod itu sudah terlalu lama.",
    ChallengeLocked: "Minta kod baharu dan mula semula.",
    NoKey: "Anda tidak boleh melihat surat-surat ini lagi.",
    AccountClosing: "Nura sudah berhenti menyimpan surat-surat ini.",
    OutOfScope: "Bahagian surat-surat ini tidak dibuka untuk anda.",
    OutOfRegion: "Surat-surat ini disimpan di negara lain.",
    NotTheirsToRead: "Hanya pemilik boleh melihat ini.",
    NotTheirKeyToCut: "Hanya pemilik boleh berkongsi surat-surat ini.",
    NoSuchHolder: "Nura tidak kenal orang itu.",
    NoConsent: "Pemilik belum setuju dengan ini.",
    ConsentWithheld: "Pemilik masih belum setuju dengan ini.",
    NotTheirConsentToGive: "Hanya pemilik boleh setuju dengan ini.",
    NotTheirConsentToWithdraw: "Hanya pemilik boleh hentikan ini.",
    NotTheClaimant: "Surat-surat ini disediakan untuk orang lain.",
    NotTheirsToChange: "Anda boleh melihat ubat tetapi tidak boleh mengubahnya.",
    NoConsentToWithdraw: "Tidak ada apa-apa untuk dihentikan.",
    NoKeyToClose: "Perkongsian itu sudah dihentikan.",
    NoStewardshipHere: "Surat-surat ini tidak disediakan untuk orang lain.",
    NoState: "Nura belum ada apa-apa untuk ditunjukkan.",
    NoSuchReviewCard: "Kad itu sudah tiada di sini.",
    NoSuchLine: "Ubat itu tiada dalam senarai anda.",
    PhotoTooLarge: "Foto itu terlalu besar untuk Nura.",
    ProfileAlreadyOwned: "Anda sudah ada surat-surat anda sendiri.",
    AlreadyConfirmed: "Anda sudah setuju dengan ini.",
    AlreadyRecorded: "Nura sudah ada ini.",
    AlreadyRegistered: "Nombor ini sudah didaftarkan.",
    AlreadySetUp: "Surat-surat untuk nombor ini sudah disediakan.",
    WaitingToBeClaimed: "Ada surat-surat menunggu anda kata ya.",
    NotTheCurrentWording: "Kata-kata itu sudah berubah sejak anda membacanya.",
    WordingNotOnFile: "Nura tidak ada kata-kata itu.",
    NotWhatWasConfirmed: "Itu bukan apa yang anda setujui.",
    NotAConfirmerHere: "Hanya anda boleh setuju dengan ini.",
    HighRiskNeedsLabelPhoto: "Sila ambil foto label ubat ini dahulu.",
    NoProvenance: "Nura perlu tahu dari mana ini datang.",
    NoWordsInThatLanguage: "Nura belum ada kata-kata ini dalam bahasa itu.",
    NotAPhoto: "Nura hanya boleh terima foto di sini.",
    NothingBehindTheBasis: "Nura perlu tahu mengapa anda menjaga mereka.",
    NotAgreedPerPerson: "Pemilik belum setuju membenarkan orang ini masuk.",
    NotForYourself: "Guna pintu yang satu lagi untuk menyimpan surat-surat anda sendiri.",
    ConfirmationExpired: ["Ya itu sudah terlalu lama.", "Sila setuju sekali lagi."],
    AlreadySpent: "Anda sudah setuju dengan ini.",
    NoSuchItem: "Kad itu sudah tiada di sini.",
    NoCachedPage: "Nura belum simpan halaman untuk anda.",
    NotACursor: "Nura tidak jumpa kad seterusnya.",
    NotAConsultRecording: "Nura tidak dapat menyimpan rakaman itu.",
    ConsultTooLong: "Rakaman itu terlalu panjang untuk Nura.",
    NoSuchRecording: "Rakaman itu sudah tiada di sini.",
    NotAClip: "Nura tidak dapat mencari bahagian rakaman itu.",
    OnlyTheFamilyHears: "Hanya pemilik dan keluarga yang dia benarkan boleh mendengar ini.",
    ChunkTooLarge: "Bahagian rakaman itu terlalu besar untuk Nura.",
    UploadClosed: "Nura tidak lagi menyimpan rakaman itu.",
    NotYourUpload: "Hanya telefon yang mula merakam boleh menghantarnya.",
    NoYesFromTheDoctor: "Nura hanya simpan rakaman selepas doktor kata boleh.",
    NoSuchUpload: "Nura tidak dapat mencari rakaman itu.",
    NotTheirsToChangeVisits: "Anda boleh lihat lawatan tetapi tidak boleh mengubahnya.",
    NotAChief: ["Hanya pemilik boleh buat ini.", "Orang yang menjaga surat-surat ini juga boleh."],
    NotOnThisVisit: "Nura tidak boleh beri tugas memandu ini kepada orang itu.",
    TapNotToday: "Nura hanya menulis apa yang anda tekan hari ini.",
    // A body too large to take, answered for the app by a layer in front of it (a bare 413).
    TooLarge: "Dokumen itu terlalu besar untuk Nura.",
    NoteNamesHealth: "Nura tidak boleh simpan nota yang menyebut ubat atau penyakit.",
    NotAPlaceNote: "Sila tulis satu baris pendek tentang tempat itu.",
    NotTheirsToSet: "Anda boleh lihat hari itu tetapi tidak boleh mengubahnya.",
    NotARoutine: "Waktu mesti mengikut urutan sepanjang hari.",
    NoSuchAnalyte: "Nura tidak kenal ujian itu.",
    NobodyToAsk: ["Tiada sesiapa dalam senarai keluarga untuk diminta.", "Tambah seseorang ke senarai keluarga dahulu."],
    NotACount: "Sila taip berapa banyak, sebagai nombor.",
    AlreadyHangsThere: "Surat itu sudah ada di situ.",
    EpisodeAlreadyClosed: "Sakit ini sudah berakhir.",
    NoSuchEpisode: "Sakit itu tiada di sini lagi.",
    NoSuchProvider: "Doktor itu tiada dalam senarai anda.",
    StaleState: ["Nura masih mengemas kini.", "Sila cuba lagi."],
    NotIdentified: "Nura tidak dapat mencari ubat ini.",
    StrengthNotRead: [
      "Nura tahu ubat ini tetapi tidak tahu berapa kuat ubat ini.",
      "Ambil gambar label sekali lagi supaya nampak berapa kuat ubat ini.",
    ],
    DoseNotRead: "Sila taip cara mengambilnya, seperti pada label.",
    NotADose: "Nura tidak faham cara mengambilnya.",
    WouldWiden: ["Nura tidak boleh meluaskan ini.", "Pemilik perlu setuju dengan lebih dahulu."],
    NothingToNarrow: "Itu tidak akan mengubah apa-apa.",
    NotTheDoer: "Hanya orang yang diberi tugas boleh kata ia sudah siap.",
    AlreadyDone: "Ini sudah siap.",
    NotTheOwner: "Hanya pemilik boleh buat ini.",
    AlreadyMarked: "Bahagian ini sudah disimpan untuk pemilik.",
    NotMarked: "Bahagian ini sudah dibuka.",
    NotAPartToMark: "Kad kecemasan sentiasa dibuka untuk keluarga.",
    NotOwnerOrChief: ["Hanya pemilik boleh melihat ini.", "Orang yang menjaga surat-surat ini juga boleh."],
    NotStaff: "Hanya ahli farmasi Nura boleh membuka ini.",
    NoSuchSlot: "Giliran itu sudah tiada dalam senarai.",
    NoSuchTask: "Tugasan itu sudah tiada di sini.",
    NotADuty: "Sila pilih hari dan masanya.",
    NotOnThisProfile: "Orang itu tidak boleh melihat surat-surat ini.",
    NoSuchTemplate: "Nura tidak ada mesej itu.",
    MissingSlot: "Sila isi setiap bahagian mesej.",
    NotAMemo: "Sila tulis 1 hingga 6 baris pendek.",
    BadWindow: "Sila pilih masa yang belum berlalu.",
    NotPlainWords: "Sila guna perkataan yang lebih mudah.",
    NotAMessage: "Sila tulis mesej yang pendek.",
    NotTheirsToConnect: ["Hanya pemilik boleh menambah kalendar.", "Orang yang menjaga surat-surat ini juga boleh."],
    NotTheirsToDecide: "Anda boleh lihat lawatan ini tetapi tidak boleh memutuskannya.",
    AlreadyDecided: "Seseorang sudah menjawab yang ini.",
    NoSuchConnector: "Sila tambah dokumen kalendar sekali lagi.",
    NoSuchProposal: "Lawatan itu sudah tiada di sini.",
    NotACalendar: "Nura tidak dapat membaca dokumen kalendar itu.",
    ConsentRevoked: "Pemilik sudah hentikan ini.",
    ConsentOutOfDate: "Pemilik perlu setuju dengan kata-kata baharu dahulu.",
    AlreadyReviewed: "Seseorang sudah memutuskan yang ini.",
    NoSuchReviewItem: "Perkara itu sudah tiada dalam senarai.",
    NotWellFormed: "Nura tidak faham itu.",
    AlertsAreNeverHeld: "Mesej yang tidak boleh tunggu tidak pernah ditahan.",
    AlertsGoEveryWay: "Nura sentiasa beritahu keluarga anda tentang ini, dengan setiap cara yang boleh.",
    MessageNamesAMedicine: ["Mesej tidak boleh menyebut ubat atau berapa banyak perlu diambil.", "Nura hantar peringatan ubat hanya daripada senarai ubat."],
    NotOnTheLadder: "Nura tidak minta anda tentang yang ini.",
    NotADocument: "Nura hanya boleh simpan dokumen atau foto di sini.",
    StopsByClosingTheAccount: "Untuk hentikan Nura menyimpan surat-surat anda, tutup akaun anda.",
    DocumentTooLarge: "Dokumen itu terlalu besar untuk Nura.",
    CalendarTooLarge: "Dokumen kalendar itu terlalu besar untuk Nura.",
  },
} satisfies Strings;
