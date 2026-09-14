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
    useEmail: "Daftar masuk dengan emel",
    // @patient phrase
    usePhone: "Daftar masuk dengan nombor telefon",
    // @patient
    codeLead: "Kami sudah hantar kod ke telefon anda.",
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
    linkLead: "Kami sudah hantar pautan ke emel anda.",
    // @patient
    linkHint: "Tampal kod daripada emel itu di sini.",
    // @patient phrase
    linkLabel: "Kod daripada emel",
    // @patient
    never: "Nura tidak akan menelefon anda untuk meminta kod ini.",
    // @patient
    wait: "Sekejap.",
    // @patient phrase
    back: "Kembali",
  },
  doors: {
    // @patient headline
    title: "Ini untuk siapa?",
    // @patient phrase
    forMe: "Ini untuk saya",
    // @patient
    forMeLine: "Nura akan menyimpan rekod anda sendiri.",
    // @patient phrase
    forSomeone: "Ini untuk orang lain",
    // @patient
    forSomeoneLine: "Anda akan menjaga rekod mereka untuk mereka.",
    // @patient phrase
    invited: "Seseorang membenarkan saya masuk",
    // @patient
    invitedLine: "{name} berkongsi rekod dengan anda.",
    // @patient phrase
    waiting: "Ada rekod menunggu anda",
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
    title: "Rekod ini milik anda",
    // @patient
    setUpBy: "{name}, {relationship}, menyediakan ini untuk anda.",
    // @patient
    keepsSeeing: "{name} akan terus melihat bahagian ini:",
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
    title: "Rekod siapa?",
    // @patient phrase
    own: "Rekod anda sendiri",
    // @patient
    roleOwner: "Ini rekod anda sendiri.",
    // @patient
    roleChief: "Anda menjaga rekod ini.",
    // @patient
    roleCaregiver: "Anda boleh melihat sebahagian rekod ini.",
    // @patient
    roleSteward: "Anda menyediakan ini untuk mereka.",
    // @patient
    roleOther: "Anda boleh melihat rekod ini.",
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
    tookMorning: "Anda sudah ambil pagi ini.",
    // @patient
    tookAfternoon: "Anda sudah ambil tengah hari ini.",
    // @patient
    tookEvening: "Anda sudah ambil petang ini.",
    // @patient
    tookNight: "Anda sudah ambil malam ini.",
    // @patient
    allTaken: "Anda sudah ambil semua ubat untuk hari ini.",
    // @patient
    allTakenSub: "Tidak ada lagi yang perlu diambil hari ini.",
    // @patient
    noMedicines: "Nura belum ada ubat untuk anda.",
    // @patient
    noMedicinesSub: "Keluarga anda boleh menambahnya daripada label ubat.",
    // @patient phrase
    hear: "Dengar",
    // @patient headline
    readingTitle: "Tekanan darah anda",
    // @patient
    readingLead: "Tulis bacaan pagi ini.",
    // @patient phrase
    readingButton: "Tulis",
    // @patient
    stateStable: "Hari anda tenang.",
    // @patient
    stateWatch: "Ada sesuatu yang perlu diperhatikan.",
    // @patient
    stateAct: "Ada sesuatu yang perlu dibuat hari ini.",
    // @patient
    boundary1: "Ini bukan nasihat doktor.",
    // @patient
    boundary2: "Tanya doktor anda.",
    // @patient
    proud: "Anda sudah ambil ubat anda pada {count} hari.",
    // @patient
    proudOne: "Anda sudah ambil ubat anda pada 1 hari.",
    // @patient
    proudNone: "Kali pertama anda tekan Sudah ambil akan tercatat di sini.",
    // @patient
    proudSub: "Nombor ini hanya naik.",
    // @patient headline
    supplyTitle: "Ubat anda",
    // @patient
    offline: "Anda tidak ada talian sekarang.",
    // @patient
    offlineSub: "Ini halaman Hari Ini anda daripada sebelum ini.",
    // @patient
    homeScreen1: "Anda boleh tambah Nura ke skrin utama anda.",
    // @patient
    homeScreen2: "Tekan Kongsi, kemudian Tambah ke Skrin Utama.",
    // @patient
    fromToday: "Daripada halaman Hari Ini anda.",
  },
  reading: {
    // @patient headline
    title: "Tekanan darah anda",
    // @patient
    lead: "Taip dua nombor daripada mesin itu.",
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
    caregiver: "Kecil dan penuh",
    // @patient phrase
    switchProfile: "Lihat rekod lain",
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
    ChallengeLocked: "Terlalu banyak cubaan untuk kod itu.",
    NoKey: "Anda tidak boleh melihat rekod ini lagi.",
    OutOfScope: "Bahagian rekod ini tidak dibuka untuk anda.",
    OutOfRegion: "Rekod ini disimpan di negara lain.",
    NotTheirsToRead: "Hanya pemilik boleh melihat ini.",
    NotTheirKeyToCut: "Hanya pemilik boleh berkongsi rekod ini.",
    NoSuchHolder: "Nura tidak kenal orang itu.",
    NoConsent: "Pemilik belum setuju dengan ini.",
    ConsentWithheld: "Pemilik belum setuju dengan ini.",
    NotTheirConsentToGive: "Hanya pemilik boleh setuju dengan ini.",
    NotTheirConsentToWithdraw: "Hanya pemilik boleh hentikan ini.",
    NotTheClaimant: "Rekod ini disediakan untuk orang lain.",
    NotTheirsToChange: "Anda boleh melihat ubat tetapi tidak boleh mengubahnya.",
    NoConsentToWithdraw: "Tidak ada apa-apa untuk dihentikan.",
    NoKeyToClose: "Perkongsian itu sudah dihentikan.",
    NoStewardshipHere: "Tiada siapa menyediakan rekod ini untuk orang lain.",
    NoState: "Nura belum ada apa-apa untuk ditunjukkan.",
    NoSuchReviewCard: "Kad itu sudah tiada di sini.",
    NoSuchLine: "Ubat itu tiada dalam senarai anda.",
    PhotoTooLarge: "Foto itu terlalu besar untuk Nura.",
    ProfileAlreadyOwned: "Anda sudah ada rekod anda sendiri.",
    AlreadyConfirmed: "Anda sudah setuju dengan ini.",
    AlreadyRecorded: "Nura sudah ada ini.",
    AlreadyRegistered: "Nombor ini sudah didaftarkan.",
    AlreadySetUp: "Rekod untuk nombor ini sudah disediakan.",
    WaitingToBeClaimed: "Ada rekod menunggu untuk anda tuntut.",
    NotTheCurrentWording: "Kata-kata itu sudah berubah sejak anda membacanya.",
    WordingNotOnFile: "Nura tidak ada kata-kata itu.",
    NotWhatWasConfirmed: "Itu bukan apa yang anda setujui.",
    NotAConfirmerHere: "Hanya anda boleh setuju dengan ini.",
    HighRiskNeedsLabelPhoto: "Ubat ini perlukan foto labelnya dahulu.",
    NoProvenance: "Nura perlu tahu dari mana ini datang.",
    NoWordsInThatLanguage: "Nura belum ada kata-kata ini dalam bahasa itu.",
    NotAPhoto: "Nura hanya boleh terima foto di sini.",
    NothingBehindTheBasis: "Nura perlu tahu mengapa anda buat ini untuk mereka.",
    NotAgreedPerPerson: "Pemilik belum setuju membenarkan orang ini masuk.",
  },
} satisfies Strings;
