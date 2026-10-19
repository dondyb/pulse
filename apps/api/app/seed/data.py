"""Fictional demo data. All businesses are invented and every email address uses
the reserved `.example` top-level domain (RFC 2606), so nothing is deliverable."""

FIRST_NAMES = [
    "Budi", "Siti", "Agus", "Dewi", "Rizky", "Putri", "Andi", "Ayu", "Fajar", "Indah",
    "Hendra", "Ratna", "Yusuf", "Nadia", "Bayu", "Larasati", "Dimas", "Wulan", "Arief", "Citra",
    "Gilang", "Maya", "Reza", "Anisa", "Teguh", "Sari", "Ilham", "Fitri", "Wahyu", "Rina",
    "Bagus", "Intan", "Eko", "Melati", "Kurnia", "Dian", "Galih", "Nurul", "Rangga", "Tiara",
    "Joko", "Kartika", "Hadi", "Yuliana", "Irfan", "Sekar", "Taufik", "Amelia", "Rudi", "Lestari",
    "Satria", "Vina", "Fikri", "Hana", "Danu", "Puspita", "Aditya", "Gita", "Yoga", "Rahma",
]

LAST_NAMES = [
    "Santoso", "Wijaya", "Saputra", "Lestari", "Pratama", "Hidayat", "Nugroho", "Kusuma", "Setiawan", "Wibowo",
    "Siregar", "Nasution", "Harahap", "Simanjuntak", "Putra", "Rahmawati", "Gunawan", "Halim", "Utomo", "Firmansyah",
    "Hakim", "Purnomo", "Susanto", "Sihombing", "Panjaitan", "Tanjung", "Lubis", "Permana", "Ramadhan", "Suryadi",
    "Hartono", "Wahyudi", "Kurniawan", "Maharani", "Anggraini", "Pangestu", "Sutanto", "Rangkuti", "Manurung", "Daulay",
]

# (company name, email domain)
COMPANIES = [
    ("PT Nusantara Logistik Digital", "nusantaralogistik.example"),
    ("Kopi Senja Bersama", "kopisenja.example"),
    ("CV Batik Larasati", "batiklarasati.example"),
    ("PT Arunika Teknologi", "arunika.example"),
    ("Toko Rempah Sentosa", "rempahsentosa.example"),
    ("PT Samudra Fintek Indonesia", "samudrafintek.example"),
    ("Klinik Sehat Medika", "sehatmedika.example"),
    ("PT Garuda Agro Lestari", "garudaagro.example"),
    ("Rumah Makan Padang Saiyo", "padangsaiyo.example"),
    ("PT Cahaya Properti Mandiri", "cahayaproperti.example"),
    ("Sinar Jaya Elektronik", "sinarjaya.example"),
    ("PT Bumi Hijau Energi", "bumihijau.example"),
    ("Akademi Cerdas Edukasi", "cerdasedukasi.example"),
    ("PT Mitra Kargo Antarpulau", "mitrakargo.example"),
    ("Dapur Nenek Catering", "dapurnenek.example"),
    ("PT Pelita Kreasi Media", "pelitakreasi.example"),
    ("Apotek Sumber Waras", "sumberwaras.example"),
    ("PT Kencana Retail Group", "kencanaretail.example"),
    ("Warung Digital Kita", "warungdigital.example"),
    ("PT Tirta Biru Hospitality", "tirtabiru.example"),
    ("Bengkel Maju Motor", "majumotor.example"),
    ("PT Langit Biru Travel", "langitbiru.example"),
    ("Studio Desain Rupa", "desainrupa.example"),
    ("PT Andalas Manufaktur", "andalasmfg.example"),
    ("Koperasi Tani Makmur", "tanimakmur.example"),
    ("PT Mega Sinergi Konsultan", "megasinergi.example"),
    ("Toko Buku Pustaka Ilmu", "pustakailmu.example"),
    ("PT Rajawali Data Solusi", "rajawalidata.example"),
    ("Salon Cantik Ayu", "cantikayu.example"),
    ("PT Semesta Pangan Nusantara", "semestapangan.example"),
    ("Kriya Kayu Jepara", "kriyajepara.example"),
    ("PT Harmoni Asuransi Mitra", "harmoniasuransi.example"),
    ("Galeri Tenun Sumba", "tenunsumba.example"),
    ("PT Prima Kesehatan Digital", "primakesehatan.example"),
    ("Laundry Bersih Kilat", "bersihkilat.example"),
    ("PT Teknindo Otomasi", "teknindo.example"),
]

SIGNATURE = "\n\nWarm regards,\nThe Pulse Team\n\nYou are receiving this because you subscribed to updates. Reply STOP to unsubscribe."

# (name, subject, body, audience, days_ago)
HISTORY = [
    (
        "Onboarding: Welcome to Your Workspace",
        "Welcome aboard — let's set up your workspace",
        "Hi there,\n\nThanks for starting your trial! Here are three quick steps to get value on day one:\n\n1. Import your customer list\n2. Invite a teammate\n3. Send your first test campaign\n\nNeed a hand? Book a 15-minute onboarding call with our Jakarta team.",
        "trial_users",
        28.3,
    ),
    (
        "Product Update: Faster Invoice Exports",
        "Invoice exports are now 4× faster",
        "Hello,\n\nWe rebuilt our export engine. Large invoice exports that used to take minutes now finish in seconds, and you can schedule recurring exports to your finance team every Monday morning.",
        "active_customers",
        25.1,
    ),
    (
        "Webinar Invite: Scaling Customer Support",
        "Webinar: Scaling customer support without burning out your team",
        "Hi,\n\nJoin us on Thursday at 14:00 WIB for a 45-minute session with support leaders from growing Indonesian businesses. We'll cover triage, macros, and measuring response quality.\n\nSeats are limited — reserve yours today.",
        "all_subscribers",
        22.4,
    ),
    (
        "Maintenance Notice: Database Upgrade",
        "Scheduled maintenance this Sunday, 01:00–03:00 WIB",
        "Hello,\n\nWe're upgrading our database cluster this Sunday between 01:00 and 03:00 WIB. The dashboard will be read-only for up to 20 minutes during this window. No action is needed on your side.",
        "all_subscribers",
        19.2,
    ),
    (
        "VIP Early Access: Analytics Dashboard",
        "You're invited: early access to the new analytics dashboard",
        "Hi,\n\nAs one of our most valued customers, you get first access to our redesigned analytics dashboard — cohort charts, revenue trends, and exportable reports. Turn it on from Settings → Labs.",
        "vip_customers",
        16.5,
    ),
    (
        "Trial Ending Reminder",
        "Your trial ends in 3 days — keep your data",
        "Hi,\n\nYour trial wraps up in three days. Choose a plan to keep your contacts, templates, and reports. Annual plans include two months free.",
        "trial_users",
        13.3,
    ),
    (
        "Monthly Product Digest — September",
        "What's new this month: bulk import, saved filters, and more",
        "Hello,\n\nThis month we shipped bulk contact import, saved table filters, and faster search. Read the full changelog for details and short how-to videos.",
        "active_customers",
        10.4,
    ),
    (
        "Security Notice: New Login Alerts",
        "New: get alerted when someone signs in to your account",
        "Hi,\n\nWe've added login alerts. You'll now receive a notification when your account is accessed from a new device. You can manage alerts from your profile settings.",
        "all_subscribers",
        7.2,
    ),
    (
        "Webinar Recap: Payment Reconciliation",
        "Recording inside: automating payment reconciliation",
        "Hello,\n\nThanks to everyone who joined last week's webinar. The recording and slide deck are now available, including the reconciliation checklist our finance team uses every month.",
        "active_customers",
        5.3,
    ),
    (
        "Customer Workshop — Surabaya",
        "Join our hands-on customer workshop in Surabaya",
        "Hi,\n\nWe're hosting a half-day workshop in Surabaya on reporting best practices. Bring your laptop and your toughest questions. Lunch is on us.",
        "vip_customers",
        3.4,
    ),
    (
        "Product Update: Saved Segments",
        "Build an audience once, reuse it everywhere",
        "Hello,\n\nSaved segments are here. Define an audience with filters once and reuse it across campaigns and reports. Segments update automatically as your contacts change.",
        "all_subscribers",
        1.3,
    ),
    (
        "Maintenance Complete: Platform Upgrade",
        "Maintenance complete — here's what improved",
        "Hi,\n\nLast night's maintenance is complete. Pages now load about 30% faster, and report generation runs on dedicated capacity. Thank you for your patience.",
        "trial_users",
        0.12,
    ),
]

# Indexes into HISTORY of campaigns that also had a manual retry run.
HISTORY_WITH_MANUAL_RETRY = {4, 5, 7, 9, 11}

DRAFTS = [
    (
        "Year-End Appreciation for VIP Customers",
        "A thank-you gift for a great year together",
        "Hi,\n\nThank you for growing with us this year. As a VIP customer, you'll receive an extended support window and a complimentary strategy session in January.",
        "vip_customers",
    ),
    (
        "Onboarding Tips: Your First Report",
        "Build your first report in five minutes",
        "Hello,\n\nReports help you spot trends early. Start with our 'Weekly Revenue' template, pick a date range, and share the link with your team.",
        "trial_users",
    ),
]

SCHEDULED = (
    "Webinar Invite: Automating Month-End Closing",
    "Live session: close your books two days faster",
    "Hi,\n\nJoin our finance automation webinar next Wednesday at 10:00 WIB. We'll walk through templates for accruals, reconciliation, and approval workflows used by Indonesian SMEs.\n\nSave your seat — the recording will be shared with registrants.",
    "trial_users",
)
