import type { Strings } from "./types";

/** Malay: a first translation awaiting a native speaker's pass, like the backend's. */
export const ms = {
  // @patient headline
  appName: "Nura",
  tabs: {
    // @patient headline
    today: "Hari Ini",
    // @patient headline
    me: "Saya",
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
    relationshipLabel: "Siapa mereka kepada anda",
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
  },
  reading: {
    // @patient headline
    title: "Tekanan darah anda",
    // @patient
    lead: "Taip 2 nombor daripada mesin itu.",
    // @patient phrase
    top: "Nombor atas",
    // @patient phrase
    bottom: "Nombor bawah",
    // @patient phrase
    save: "Simpan",
    // @patient
    saved: "Nura sudah tulis nombor itu.",
    // @patient phrase
    cancel: "Bukan sekarang",
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
    signOut: "Daftar keluar",
  },
  errors: {
    // @patient
    network: "Nura tidak dapat sambungan internet sekarang.",
    // @patient phrase
    tryAgain: "Cuba lagi",
  },
  // @patient
  refusals: {
    default: "Nura tidak dapat buat itu sekarang.",
    NoSession: "Sila daftar masuk semula.",
    NoOpenChallenge: "Minta kod baharu dahulu.",
    WrongCode: "Kod itu tidak betul.",
    ChallengeExpired: "Kod itu sudah terlalu lama.",
    ChallengeLocked: "Minta kod baharu dan mula semula.",
    NoKey: "Anda tidak boleh melihat surat-surat ini lagi.",
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
  },
} satisfies Strings;
