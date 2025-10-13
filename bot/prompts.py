# Centralized prompts for Slack bot commands

# Prompts for LLM analysis
PQF_ANALYSIS_PROMPT = """
Kamu adalah asisten QA profesional. Analisa thread berikut dan berikan hasil dalam format JSON valid seperti contoh di bawah.

THREAD:
{thread_content}

Kembalikan hanya JSON berikut (tanpa penjelasan tambahan):

{{
  "type": "menganalisis deskripsi issue atau thread diskusi di bawah ini, kemudian tentukan Type issue ke dalam salah satu kategori berikut:
                Ask → Pertanyaan, permintaan klarifikasi, atau permintaan informasi,
                Bug → Ditemukan bug, error, defect, atau malfungsi pada sistem yang harus diperbaiki,
                Feedback → Masukan untuk peningkatan, saran perbaikan UX, usability, atau usulan perubahan non-critical,
                Other → Lainnya (jika tidak ada yang sesuai)",
  "product": "Nama produk (misal: AgentLabs, LLM, Intent Base, Shopee, Email, Dialogflow, App Center, Qiscus Survey, Email Broadcast, Tiktok, Tokopedia, QCRM, CSAT, Agent Copilot atau Unknown jika tidak ada)",
  "fitur" : "Fitur yang di ambil dari hasil analisis thread merupakan fitur yang terkena bug, error, ask ,ataupun feedback",
  "description": "Ringkasan diskusi (maksimal 600 karakter, dalam bahasa Indonesia)",
  "role": "menganalisis deskripsi issue atau thread diskusi di bawah ini, lalu tentukan Role yang paling tepat untuk menangani issue tersebut:
                Backend → Backend Developer Jika issue berkaitan dengan server, API, database, logic backend,
                Frontend → Frontend Developer Jika issue berkaitan dengan tampilan UI, interaksi user, behavior di sisi klien,
                Design → UI/UX Designer Jika issue berkaitan dengan desain visual, elemen grafis, layout, UX/UI improvement,
                Other → Lainnya (jika tidak ada yang sesuai)"
  "reporter": "User ID dari user yang melaporkan/membuat thread (ambil dari PARENT MESSAGE User, contoh: U092H3HB2D7)",
  "responder": "User ID dari user yang menjawab thread (ambil dari REPLIES User, contoh: U091UAMQCF8, jika tidak ada pilih Unknown)",
  "severity": "Menganalisis deskripsi issue atau thread diskusi di bawah ini. Kemudian klasifikasikan issue tersebut ke SATU tipe berikut:
                Hotfix → Masalah kritis yang harus segera diperbaiki di produksi,
                Bugfix → Bug atau defect yang perlu diperbaiki tetapi tidak mendesak untuk langsung deploy ke produksi,
                Feature → Permintaan penambahan fitur baru atau peningkatan signifikan,
                Other (Ask) → Hal di luar ketiganya, seperti dokumentasi, tes, refactoring, atau pertanyaan",
  "urgency": " Menganalisis deskripsi issue atau diskusi thread. Kemudian tentukan prioritas/urgensi issue ke dalam salah satu tingkat berikut:
                High → Issue yang memiliki dampak besar, harus segera ditangani,
                Medium → Issue yang memiliki dampak sedang, tidak mendesak tapi perlu ditangani dalam waktu dekat,
                Low → Issue yang memiliki dampak kecil, tidak mendesak dan dapat ditangani nanti"
}}

Contoh output:
{{
  "type": "Ask",
  "product": "LLM",
  "fitur": "Export Import",
  "description": "User melaporkan error pada fitur LLM dan meminta solusi.",
  "role": "Backend",
  "reporter": "U092H3HB2D7",
  "responder": "U091UAMQCF8",
  "severity": "Bugfix",
  "urgency": "High"
}}

PENTING: 
1. Baca isi thread dengan teliti.
2. Analisis dampak & risiko issue.
3. Untuk reporter, ambil User ID dari PARENT MESSAGE. Untuk responder, ambil User ID dari REPLIES. Jangan ubah format User ID, gunakan persis seperti yang ada di data.
4. Jika hanya ada 1 pesan, tetap lakukan klasifikasi sebaik mungkin berdasarkan isi pesan.
"""

BUG_CONFIRMATION_PROMPT = "Analyze this thread and confirm if it's a bug or feedback: {thread_text}"

# Default messages
COMMAND_UNKNOWN = "Unknown command."
NO_THREAD_DATA = "No thread data available."
NO_THREAD_FOUND = "No thread found to analyze."
ANALYSIS_FAILED = "Analysis failed."
LOG_SUCCESS = "PQF analysis logged: {analysis}"
RESOLUTION_UPDATED = "Resolution updated: {resolution}"
TICKET_CREATED = "Ticket created: {item_id}"
BUG_ANALYSIS = "Analysis: {analysis}"
FAILED_PQF = "Failed to handle PQF."
FAILED_RESOLUTION = "Failed to update resolution."
FAILED_TICKET = "Failed to create ticket."
FAILED_BUG = "Failed to confirm bug."