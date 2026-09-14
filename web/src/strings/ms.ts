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
  feed: {
    // @patient headline
    title: "Lagi untuk anda",
    // @patient phrase
    open: "Lihat lagi untuk anda",
    // @patient headline
    story: "Kisah anda",
    // @patient headline
    learning: "Dalam kata-kata mudah",
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
    // @patient phrase
    back: "Kembali ke kad anda",
    // @patient
    statusHeld: "Nura tidak tunjuk kad ini kepada {name}.",
    // @patient
    statusSent: "Kad ini ada di halaman yang {name} lihat.",
    // @patient
    statusOpened: "{name} sudah buka kad ini.",
    // @patient
    statusDismissed: "{name} tekan Bukan untuk saya pada kad ini.",
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
    caregiver: "Kecil, lebih banyak dalam satu halaman",
    // @patient phrase
    lookAuto: "Biar Nura pilih",
    // @patient phrase
    switchProfile: "Lihat surat-surat orang lain",
    // @patient phrase
    setUp: "Sediakan Nura",
    // @patient phrase
    signOut: "Daftar keluar",
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
      noted: "Nura sudah catat itu.",
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
      kindDeviceScreen: "Ini skrin sebuah mesin.",
      // @patient
      unreadable: "Nura tidak dapat membaca yang ini.",
      // @patient
      typeIt: "Sila taip apa yang tertulis pada surat itu.",
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
      seeWords: "Lihat kata-kata itu",
      // @patient
      wordsLead: "Sila baca kata-kata ini.",
      // @patient phrase
      agree: "Saya setuju, benarkan mereka",
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
      // @patient phrase
      missing: "Belum ada",
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
      nothing: "Tiada apa yang tertinggal buat masa ini.",
      // @patient phrase
      open: "Buka Nura",
    },
    // @patient phrase
    fields: {
      lipid_panel: {
        total_cholesterol: "Jumlah kolesterol",
        hdl: "Kolesterol baik",
        ldl: "Kolesterol jahat",
        triglycerides: "Lemak dalam darah",
        vldl: "Satu lagi nombor lemak darah",
        tc_hdl_ratio: "Nisbah kolesterol",
        non_hdl_cholesterol: "Kolesterol tanpa bahagian baik",
      },
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
      blood_sugar: { glucose: "Nombor gula" },
      lab_report: { lab: "Tempat darah diuji" },
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
    },
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
  },
} satisfies Strings;
