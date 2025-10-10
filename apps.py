import os
import logging
import atexit
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import json
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from slack_bot import SlackBot
from gemini_hook import GeminiAnalyzer
from spreadsheet import SpreadsheetManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress DEBUG logs from slack_sdk
logging.getLogger("slack_sdk").setLevel(logging.WARNING)

# Initialize Flask app
app = Flask(__name__)

class LazyProxy:
    """Thread-safe lazy loader for heavyweight singletons."""

    def __init__(self, factory):
        self._factory = factory
        self._instance = None
        self._lock = threading.Lock()

    @property
    def initialized(self) -> bool:
        return self._instance is not None

    def _get_instance(self):
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return self._instance

    def __getattr__(self, item):
        return getattr(self._get_instance(), item)

    def __bool__(self):  # pragma: no cover - allow truthiness checks
        return True


# Initialize components lazily to avoid upfront memory spikes
slack_bot = LazyProxy(SlackBot)
gemini_analyzer = LazyProxy(GeminiAnalyzer)
spreadsheet_manager = LazyProxy(SpreadsheetManager)


def _resolve_thread_pool_size() -> int:
    """Return thread pool size from env or sensible default."""
    cpu_count = os.cpu_count() or 1
    # cap default to 4 workers to reduce idle memory footprint
    conservative_default = max(2, min(4, cpu_count))
    env_value = os.getenv('THREAD_POOL_MAX_WORKERS')
    if env_value:
        try:
            parsed = int(env_value)
            if parsed < 1:
                raise ValueError
            return parsed
        except ValueError:
            logger.warning(
                "Invalid THREAD_POOL_MAX_WORKERS value '%s'. Falling back to default %s",
                env_value,
                conservative_default,
            )
    return conservative_default


_EXECUTOR = None
_EXECUTOR_LOCK = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                max_workers = _resolve_thread_pool_size()
                _EXECUTOR = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="bot-worker",
                )
                logger.info("ThreadPoolExecutor initialized with %s workers", max_workers)
    return _EXECUTOR


def _shutdown_executor():
    global _EXECUTOR
    if _EXECUTOR is not None:
        _EXECUTOR.shutdown(wait=False)


atexit.register(_shutdown_executor)

ALLOWED_CHANNELS = os.getenv('ALLOWED_CHANNELS', '').split(',')
FORWARD_CHANNEL_ID = os.getenv('FORWARD_CHANNEL_ID', '').split(',')

def validate_and_extract_command(text):
    """
    Validate command format: [from] pqf [quarter] [year] [product]
    from: internal/eksternal
    quarter: q1/q2/q3/q4
    year: 4-digit year
    product: robolabs/appcenter
    """
    # Remove bot mention and clean text
    text = re.sub(r'<@[^>]+>', '', text).strip().lower()

    # Define validation patterns
    valid_froms = ['internal', 'eksternal']
    valid_products = ['agentlabs', 'appcenter']

    # Flexible pattern: find all required keywords in any order
    from_match = re.search(r'(internal|eksternal)', text)
    pqf_match = re.search(r'pqf', text)
    product_match = re.search(r'(agentlabs|appcenter)', text)

    if not (from_match and pqf_match and product_match):
        return None, None, "Format perintah tidak valid"

    from_value = from_match.group(1)
    product = product_match.group(1)

    # Additional validations
    if from_value not in valid_froms:
        return None, None, f"From harus 'internal' atau 'eksternal', bukan '{from_value}'"

    if product not in valid_products:
        return None, None, f"Product harus 'agentlabs' atau 'appcenter', bukan '{product}'"

    return from_value.capitalize(), product.capitalize(), None

@app.route('/slack/events', methods=['POST'])
def slack_events():
    # Cek header retry dari Slack
    if request.headers.get('X-Slack-Retry-Num'):
        return jsonify({'status': 'ignored retry'}), 200
    try:
        data = request.get_json()
        # Handle URL verification challenge
        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data.get('challenge')})
        # Handle app mention events
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            if event.get('type') == 'app_mention':
                # Jalankan handle_app_mention di worker pool
                _get_executor().submit(handle_app_mention, event)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}")
        return jsonify({'error': str(e)}), 500

def handle_app_mention(event):
    """Handle app mention events"""
    channel = event.get('channel')
    if channel not in ALLOWED_CHANNELS:
        logger.info(f"Ignored event from channel {channel} (not in allowed list)")
        return
    try:
        text = event.get('text', '')
        channel = event.get('channel')
        ts = event.get('ts')
        user = event.get('user')
        thread_ts = event.get('thread_ts')

        if not thread_ts or thread_ts == ts:
            from datetime import datetime
            slack_bot.send_message(
                channel,
                "Mohon maaf atas ketidaknyamanan yang terjadi 🙏. Terima kasih atas laporanya! Laporanmu sudah masuk ke antrian dan akan segera kami proses. Harap menunggu ya, QFolks!",
                thread_ts=ts
            )
            thread_data = slack_bot.get_thread_data(channel, ts)
            if thread_data:
                parent = thread_data.get('parent_message', {})
                parent_ts = parent.get('ts')
                #parent_text = parent.get('text', '')
                if parent_ts:
                    dt = datetime.fromtimestamp(float(parent_ts))
                    bulan = dt.month
                    tahun = dt.year
                    week_num = ((dt.day - 1) // 7) + 1
                    if 1 <= bulan <= 3:
                        quarter = 'Q1'
                    elif 4 <= bulan <= 6:
                        quarter = 'Q2'
                    elif 7 <= bulan <= 9:
                        quarter = 'Q3'
                    else:
                        quarter = 'Q4'
                    analysis = gemini_analyzer.analyze_thread(thread_data)
                    if analysis:
                        product_raw = (analysis.get('product') or '').strip().lower()
                        agentlabs_keywords = ['agentlabs', 'llm', 'intent base', 'dialogflow']
                        appcenter_keywords = ['shopee', 'email', 'qcrm', 'appcenter', 'survey', 'tokopedia', 'email broadcast', 'tiktok', 'CSAT', 'agent copilot']
                        if any(k in product_raw for k in agentlabs_keywords):
                            product_sheet = 'Agentlabs'
                        elif any(k in product_raw for k in appcenter_keywords):
                            product_sheet = 'Appcenter'
                        else:
                            product_sheet = 'Unknown'
                        if product_sheet == 'Unknown':
                            #slack_bot.send_message(channel, "Gagal catat otomatis, wajib catat manual ya QFolks! (Product tidak terdeteksi robolabs/appcenter)", thread_ts=ts)
                            import os
                            forward_channel = os.getenv('FORWARD_CHANNEL_ID')
                            if forward_channel and parent_ts:
                                user_id_slack_bot = os.getenv('USER_ID_SLACK_BOT', '')
                                month_name = dt.strftime('%B')
                                info_text = f"[{quarter}] [{tahun}] [Week {week_num}] [Date {dt.day} - {month_name}] [Tidak Tercatat] [<@{user_id_slack_bot}>]"
                                permalink = thread_data.get('permalink', '')
                                if '&cid=' in permalink:
                                    permalink = permalink.split('&cid=')[0]
                                slack_bot.client.chat_postMessage(
                                    channel=forward_channel,
                                    text=info_text + "\n" + permalink
                                )
                            return
                        sheet_name = f"{quarter} {tahun} {product_sheet.capitalize()}"
                        spreadsheet_manager.create_sheet_if_not_exists(sheet_name)
                        permalink = thread_data.get('permalink', '')
                        if '&cid=' in permalink:
                            permalink = permalink.split('&cid=')[0]
                        existing_links = [l.split('&cid=')[0] if l else l for l in spreadsheet_manager.get_all_links(sheet_name)]
                        if permalink in existing_links:
                            return
                        reporting_date_time = ''
                        if parent_ts:
                            reporting_date_time = dt.strftime('%Y-%m-%d %H:%M')
                        bot_user_id = slack_bot.client.auth_test()['user_id']
                        bot_user_info = slack_bot.get_user_info(bot_user_id)
                        bot_name = bot_user_info.get('real_name', bot_user_info.get('name', 'Bot')) if bot_user_info else 'Bot'
                        responder_name = 'Unknown'
                        response_time_str = 'Unknown'
                        for reply in thread_data.get('replies', []):
                            if reply.get('user') == bot_user_id:
                                responder_name = bot_name
                                ts_reply = reply.get('ts')
                                if ts_reply:
                                    dt_reply = datetime.fromtimestamp(float(ts_reply))
                                    response_time_str = dt_reply.strftime('%Y-%m-%d %H:%M')
                                break
                        reporter_id = analysis.get('reporter', '')
                        reporter_name = 'Unknown'
                        if reporter_id and reporter_id != 'Unknown':
                            user_info = slack_bot.get_user_info(reporter_id)
                            if user_info:
                                reporter_name = user_info.get('real_name', user_info.get('name', reporter_id))
                            else:
                                reporter_name = reporter_id
                        row_data = {
                            'from': 'Eksternal',
                            'type': analysis.get('type', 'Unknown'),
                            'product': analysis.get('product', 'Unknown'),
                            'role': '',
                            'fitur': analysis.get('fitur', 'Unknown'),
                            'reporter': reporter_name,
                            'reporting_date_time': reporting_date_time,
                            'responder': responder_name,
                            'description': analysis.get('description', 'No description'),
                            'link': permalink,
                            'response_time': response_time_str,
                            'severity': '',
                            'urgency': ''
                        }
                        success = spreadsheet_manager.prepend_row(row_data, sheet_name)
                        if success:
                            import os
                            forward_channel = os.getenv('FORWARD_CHANNEL_ID')
                            if forward_channel:
                                permalink = thread_data.get('permalink', '')
                                if '&cid=' in permalink:
                                    permalink = permalink.split('&cid=')[0]
                                    month_name = dt.strftime('%B')
                                info_text = f"[{quarter}] [{tahun}] [Week {week_num}] [Date {dt.day} - {month_name}] [Tercatat]"
                                slack_bot.client.chat_postMessage(
                                    channel=forward_channel,
                                    text=info_text + "\n" + permalink
                                )
            return

        # Jika reply (bukan parent), baru proses pqf dan validasi
        text_lower = text.lower()
        if 'pqf' in text_lower:
            if channel not in FORWARD_CHANNEL_ID:
                slack_bot.send_message(
                    channel,
                    "Saat ini bot tidak dapat menindaklanjuti issue melalui kolom komentar. Informasi terkait bug/issue/feedback tersebut sudah kami terima dan sedang diproses oleh tim kami. Pembaruan dan respon akan disampaikan oleh tim kami setelah ada perkembangan lebih lanjut. Terimakasih.",
                    thread_ts=ts
                )
                return
            from_value, product, error_message = validate_and_extract_command(text)
            if error_message:
                help_message = """
                Saat ini bot tidak dapat menindaklanjuti issue melalui kolom komentar. Informasi terkait bug/issue/feedback tersebut sudah kami terima dan sedang diproses oleh tim kami. Pembaruan dan respon akan disampaikan oleh tim kami setelah ada perkembangan lebih lanjut. Terimakasih.
                """
                slack_bot.send_message(channel, help_message, thread_ts=ts)
                return
            if from_value is None or product is None:
                logger.info(f" Terjadi kesalahan dalam memproses perintah. {ts}")
                return

            # --- Ambil thread_data dari thread asli jika event terjadi di channel forward ---
            def parse_slack_permalink(permalink):
                import re
                match = re.search(r'/archives/([A-Z0-9]+)/p(\d+)', permalink)
                thread_ts_real = None
                channel_real = None
                if match:
                    channel_real = match.group(1)
                    ts_str = match.group(2)
                    if len(ts_str) > 6:
                        ts = ts_str[:10] + '.' + ts_str[10:]
                        thread_ts_real = ts
                m2 = re.search(r'thread_ts=(\d+\.\d+)', permalink)
                if m2:
                    thread_ts_real = m2.group(1)
                return channel_real, thread_ts_real

            thread_data = slack_bot.get_thread_data(channel, ts)
            parent = thread_data.get('parent_message', {}) if thread_data else {}
            # Jika event terjadi di channel forward dan parent_message punya permalink, ambil thread_data asli
            channel_real, thread_ts_real = None, None
            if parent and parent.get('permalink') and parent.get('ts'):
                permalink = parent.get('permalink')
                channel_real, thread_ts_real = parse_slack_permalink(permalink.split('?')[0])
            elif parent and parent.get('text'):
                import re
                text_parent = parent.get('text','')
                match = re.search(r'<(https://[^>]+)>', text_parent)
                if match:
                    permalink = match.group(1)
                    channel_real, thread_ts_real = parse_slack_permalink(permalink.split('?')[0])
            if channel_real and thread_ts_real:
                logger.info(f"handle_app_mention: Ambil thread_data dari thread asli: channel={channel_real}, thread_ts={thread_ts_real}")
                thread_data = slack_bot.get_thread_data(channel_real, thread_ts_real)
            # --- END ---

            if thread_data:
                # Ambil quarter dan year dari reporting_date_time (parent_ts)
                parent = thread_data.get('parent_message', {})
                parent_ts = parent.get('ts')
                if parent_ts:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(float(parent_ts))
                    bulan = dt.month
                    tahun = dt.year
                    if 1 <= bulan <= 3:
                        quarter = 'Q1'
                    elif 4 <= bulan <= 6:
                        quarter = 'Q2'
                    elif 7 <= bulan <= 9:
                        quarter = 'Q3'
                    else:
                        quarter = 'Q4'
                    sheet_name = f"{quarter} {tahun} {product}"
                else:
                    sheet_name = f"Thread Analysis"
                permalink = thread_data.get('permalink', '')
                if '&cid=' in permalink:
                    permalink = permalink.split('&cid=')[0]
                existing_links = [l.split('&cid=')[0] if l else l for l in spreadsheet_manager.get_all_links(sheet_name)]
                if permalink in existing_links:
                    slack_bot.send_message(
                        channel, 
                        f"<@{user}> Thread ini sudah pernah dianalisis dan dicatat di spreadsheet.",
                        thread_ts=ts
                    )
                else:
                    _get_executor().submit(process_thread_data, thread_data, channel, user, ts, from_value, sheet_name)
                    slack_bot.send_message(
                        channel,
                        f"✅ Sudah masuk ke List PQF",
                        thread_ts=ts
                    )
            else:
                slack_bot.send_message(
                    channel, 
                    f"<@{user}> Tidak dapat mengambil data thread. Pastikan bot dipanggil dalam sebuah thread.",
                    thread_ts=ts
                )
        elif 'resolution' in text_lower:
            _get_executor().submit(process_resolution_or_resolve_command, event, text_lower)
        elif 'resolve' in text_lower:
            _get_executor().submit(process_resolution_or_resolve_command, event, text_lower)
        elif 'ticket' in text_lower:
            process_ticket_command(channel, thread_ts=ts)
        elif 'confirm bug' in text_lower or 'feedback' in text_lower:
            # Ambil sheet_name dari command terakhir jika ada, atau fallback
            from_value, sheet_name, _ = validate_and_extract_command(text)
            if not sheet_name:
                sheet_name = 'Thread Analysis'
            slack_bot.send_message(
                channel,
                f"Laporanmu sudah masuk ke list PQF di sheet {sheet_name} untuk proses tindak lanjut, ya QFolks!",
                thread_ts=ts
            )
            return
        else:
            help_message = """
            Saat ini bot tidak dapat menindaklanjuti issue melalui kolom komentar. Informasi terkait bug/issue/feedback tersebut sudah kami terima dan sedang diproses oleh tim kami. Pembaruan dan respon akan disampaikan oleh tim kami setelah ada perkembangan lebih lanjut. Terimakasih.
            """
            slack_bot.send_message(channel, help_message, thread_ts=ts)
    except Exception as e:
        logger.error(f"Gagal catat ke list PQF, silakan catat manual boss: {str(e)}")
        help_message = """
            Saat ini bot tidak dapat menindaklanjuti issue melalui kolom komentar. Informasi terkait bug/issue/feedback tersebut sudah kami terima dan sedang diproses oleh tim kami. Pembaruan dan respon akan disampaikan oleh tim kami setelah ada perkembangan lebih lanjut. Terimakasih.
            """
        slack_bot.send_message(channel, help_message, thread_ts=ts)

def process_thread_data(thread_data, channel, user, thread_ts, from_value="Internal", sheet_name="Thread Analysis"):
    """Process thread data with Gemini AI and save to spreadsheet"""
    try:
        # Always initialize ts with thread_ts (from mention)
        permalink = thread_data.get('permalink', '')
        if '&cid=' in permalink:
            permalink = permalink.split('&cid=')[0]
        existing_links = [l.split('&cid=')[0] if l else l for l in spreadsheet_manager.get_all_links(sheet_name)]
        if permalink in existing_links:
            slack_bot.send_message(
                channel,
                f"<@{user}> Thread ini sudah pernah dianalisis dan dicatat di spreadsheet.",
                thread_ts=thread_ts
            )
            return

        analysis = gemini_analyzer.analyze_thread(thread_data)
        if analysis:
            reporter_id = analysis.get('reporter', '')
            reporter_name = 'Unknown'
            if reporter_id and reporter_id != 'Unknown':
                user_info = slack_bot.get_user_info(reporter_id)
                if user_info:
                    reporter_name = user_info.get('real_name', user_info.get('name', reporter_id))
                else:
                    reporter_name = reporter_id

            responder_names = []
            response_time = ''
            first_response_ts = None
            found_reply = False
            if thread_data.get('replies'):
                for reply in thread_data['replies']:
                    user_id = reply.get('user')
                    if user_id:
                        user_info = slack_bot.get_user_info(user_id)
                        if user_info:
                            profile = user_info.get('profile', {})
                            email = profile.get('email', '').lower()
                            if email in ['asyrof@qiscus.com', 'faris@qiscus.com', 'rahmad@qiscus.net', 'donoquip@gmail.com']:
                                reply_ts = reply.get('ts')
                                if reply_ts and (first_response_ts is None or float(reply_ts) < float(first_response_ts)):
                                    first_response_ts = reply_ts
                                    found_reply = True
                for reply in thread_data['replies']:
                    user_id = reply.get('user')
                    if user_id:
                        user_info = slack_bot.get_user_info(user_id)
                        if user_info:
                            profile = user_info.get('profile', {})
                            email = profile.get('email', '').lower()
                            if email in ['asyrof@qiscus.com', 'faris@qiscus.com', 'rahmad@qiscus.net', 'donoquip@gmail.com']:
                                responder_name = user_info.get('real_name', user_info.get('name', user_id))
                                if responder_name not in responder_names:
                                    responder_names.append(responder_name)
            # Fallback: if no reply from whitelist, use parent message (mention)
            if not found_reply:
                parent = thread_data.get('parent_message', {})
                parent_ts = parent.get('ts')
                if parent_ts:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(float(parent_ts))
                    response_time = dt.strftime('%Y-%m-%d %H:%M')
                    # Ambil nama bot dari Slack API
                    bot_user_id = slack_bot.client.auth_test()['user_id']
                    bot_user_info = slack_bot.get_user_info(bot_user_id)
                    bot_name = bot_user_info.get('real_name', bot_user_info.get('name', 'Bot')) if bot_user_info else 'Bot'
                    responder_names = [bot_name]
            else:
                if first_response_ts:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(float(first_response_ts))
                    response_time = dt.strftime('%Y-%m-%d %H:%M')
            reporting_date_time = ''
            parent = thread_data.get('parent_message', {})
            parent_ts = parent.get('ts')
            #parent_text = parent.get('text', '')
            if parent_ts:
                from datetime import datetime
                dt = datetime.fromtimestamp(float(parent_ts))
                reporting_date_time = dt.strftime('%Y-%m-%d %H:%M')
            responder_name = ', '.join(responder_names) if responder_names else 'Unknown'
            row_data = {
                'from': from_value,
                'type': analysis.get('type', 'Unknown'),
                'product': analysis.get('product', 'Unknown'),
                'role': analysis.get('role', 'Unknown'),
                'fitur': analysis.get('fitur', 'Unknown'),
                'reporter': reporter_name,
                'reporting_date_time': reporting_date_time,
                'responder': responder_name,
                'description': analysis.get('description', 'No description'),
                'link': permalink,
                'response_time': response_time,
                'severity': analysis.get('severity', 'Others (Ask)'),
                'urgency': analysis.get('urgency', 'Medium')
            }
            logger.info(f"Attempting to prepend row to sheet: {sheet_name}")
            success = spreadsheet_manager.prepend_row(row_data, sheet_name)
            if success:
                logger.info(f"Successfully added row to sheet: {sheet_name}")
            else:
                logger.error(f"Failed to add row to sheet: {sheet_name}")
                slack_bot.send_message(
                    channel,
                    f"<@{user}> ❌ Analisis berhasil, tetapi gagal menyimpan ke spreadsheet {sheet_name}.",
                    thread_ts=thread_ts
                )
        else:
            slack_bot.send_message(
                channel,
                f"<@{user}> ❌ Gagal menganalisis thread dengan Gemini AI.",
                thread_ts=thread_ts
            )
    except Exception as e:
        logger.error(f"Error processing thread data: {str(e)}")
        logger.error(traceback.format_exc())
        slack_bot.send_message(
            channel,
            f"<@{user}> ❌ Terjadi kesalahan saat memproses thread: {str(e)}",
            thread_ts=thread_ts
        )

def process_resolution_or_resolve_command(event, text_lower):
    channel = event.get('channel')
    ts = event.get('ts')
    user = event.get('user')
    thread_ts = event.get('thread_ts') or ts

    # Ambil data thread
    thread_data = slack_bot.get_thread_data(channel, thread_ts)
    if not thread_data:
        slack_bot.send_message(channel, f"<@{user}> Tidak dapat mengambil data thread.", thread_ts=ts)
        return

    permalink = thread_data.get('permalink', '')
    if '&cid=' in permalink:
        permalink = permalink.split('&cid=')[0]

    # Cari sheet yang mengandung link ini
    found = False
    for sheet_name in spreadsheet_manager.get_available_sheets():
        links = [l.split('&cid=')[0] if l else l for l in spreadsheet_manager.get_all_links(sheet_name)]
        if permalink in links:
            # Update kolom yang sesuai
            from datetime import datetime
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'resolution' in text_lower:
                updated = spreadsheet_manager.update_column_by_link(sheet_name, permalink, 'Resolution Time', now)
                col_name = "Resolution Time"
            elif 'resolve' in text_lower:
                updated = spreadsheet_manager.update_column_by_link(sheet_name, permalink, 'Deployment Time', now)
                col_name = "Deployment Time"
            # Ambil nama reporter dari thread
            reporter_name = "Reporter"
            reporter_id = None
            # Coba ambil dari thread_data['reporter'] jika ada
            if thread_data.get('reporter'):
                reporter_id = thread_data.get('reporter')
            else:
                # Coba ambil dari analysis jika ada
                analysis = None
                try:
                    analysis = gemini_analyzer.analyze_thread(thread_data)
                except Exception:
                    analysis = None
                if analysis and analysis.get('reporter'):
                    reporter_id = analysis.get('reporter')
            if reporter_id:
                # Gunakan mention jika reporter_id ada
                reporter_name = f"<@{reporter_id}>"
            else:
                # Fallback ke nama jika tidak ada id
                user_info = slack_bot.get_user_info(reporter_id)
                if user_info:
                    reporter_name = user_info.get('real_name', user_info.get('name', 'Reporter'))
            if updated:
                if 'resolution' in text_lower:
                    custom_message = f"Halo {reporter_name} 👋\n\nLaporan yang anda sampaikan sudah selesai direproduksi dan dianalisis.\nSolusinya juga sudah ditemukan dan saat ini sedang dalam tahap pengerjaan.\nSTATUS: 🚧 On Progress - Dev Team.\nKami akan memberikan informasi selanjutnya setelah proses pengerjaan selesai.Terima kasih atas kesabarannya! 🙏\n\nSalam,\nTim Profeat"
                elif 'resolve' in text_lower:
                    custom_message = f"Halo {reporter_name} 👋\n\nLaporan telah terselesaikan dan perbaikan sudah diimplementasikan serta aktif di sistem! 🚀\nApabila masih ditemukan kendala setelah implementasi, silakan informasikan kembali.\nTerima kasih atas laporan serta kolaborasinya 🙏.\n\nSalam,\nTim Profeat"
                slack_bot.send_message(channel, custom_message, thread_ts=ts)
            else:
                slack_bot.send_message(channel, f"<@{user}> Gagal update kolom *{col_name}* pada sheet *{sheet_name}*.", thread_ts=ts)
            found = True
            break
    if not found:
        slack_bot.send_message(channel, f"<@{user}>Saat ini bot tidak dapat menindaklanjuti issue melalui kolom komentar.Kami sudah mencatat informasi ini dan akan menindaklanjutinya secara manual. Terima kasih atas kesabarannya!", thread_ts=ts)

def process_ticket_command(channel, thread_ts=None):
    """Catat thread ke sheet bug saat mention 'ticket' hanya pada channel B dan hanya jika text 'ticket'."""
    import re

    # Helper: parse channel and thread_ts from Slack permalink
    def parse_slack_permalink(permalink):
        # Example: https://.../archives/C09KQAF0GBA/p1759804695537539?thread_ts=1759804695.537539
        match = re.search(r'/archives/([A-Z0-9]+)/p(\d+)', permalink)
        thread_ts = None
        channel_id = None
        if match:
            channel_id = match.group(1)
            ts_str = match.group(2)
            # Slack ts: 1759804695.537539 -> 1759804695537539 (remove dot)
            if len(ts_str) > 6:
                ts = ts_str[:10] + '.' + ts_str[10:]
                thread_ts = ts
        # Try to get thread_ts from query param if available
        m2 = re.search(r'thread_ts=(\d+\.\d+)', permalink)
        if m2:
            thread_ts = m2.group(1)
        return channel_id, thread_ts


    # WAJIB: Ambil thread_data dari thread aslinya (bukan forward)
    # 1. Ambil permalink dari thread awal (dari parameter)
    thread_data_forward = slack_bot.get_thread_data(channel, thread_ts)
    parent_forward = thread_data_forward.get('parent_message', {}) if thread_data_forward else {}
    # WAJIB: Ambil permalink dan thread_ts dari parent_message (thread asli)
    if parent_forward and parent_forward.get('permalink') and parent_forward.get('ts'):
        permalink = parent_forward.get('permalink')
        thread_ts_real = parent_forward.get('ts')
        channel_real, _ = parse_slack_permalink(permalink.split('?')[0])
        logger.info(f"process_ticket_command: Ambil dari parent_message: channel={channel_real}, thread_ts={thread_ts_real}, permalink={permalink}")
    elif parent_forward and parent_forward.get('text'):
        # Coba parsing permalink dari text parent_message
        import re
        text = parent_forward.get('text','')
        match = re.search(r'<(https://[^>]+)>', text)
        if match:
            permalink = match.group(1)
            channel_real, thread_ts_real = parse_slack_permalink(permalink.split('?')[0])
            logger.info(f"process_ticket_command: Ambil dari parent_message TEXT: channel={channel_real}, thread_ts={thread_ts_real}, permalink={permalink}")
        else:
            logger.error(f"process_ticket_command: Tidak menemukan permalink di text parent_message. parent_message={parent_forward}")
            # Fallback: cek thread_data_forward.get('permalink')
            if thread_data_forward and thread_data_forward.get('permalink'):
                fallback_permalink = thread_data_forward.get('permalink')
                channel_real, thread_ts_real = parse_slack_permalink(fallback_permalink.split('?')[0])
                logger.info(f"process_ticket_command: Fallback dari thread_data_forward.get('permalink'): channel={channel_real}, thread_ts={thread_ts_real}, permalink={fallback_permalink}")
            else:
                logger.error(f"process_ticket_command: Tidak menemukan fallback permalink pada thread_data_forward. thread_data_forward={thread_data_forward}")
                return
    else:
        logger.error(f"process_ticket_command: Tidak menemukan permalink/ts pada parent_message thread forward. parent_message={parent_forward}")
        # Fallback: cek thread_data_forward.get('permalink')
        if thread_data_forward and thread_data_forward.get('permalink'):
            fallback_permalink = thread_data_forward.get('permalink')
            channel_real, thread_ts_real = parse_slack_permalink(fallback_permalink.split('?')[0])
            logger.info(f"process_ticket_command: Fallback dari thread_data_forward.get('permalink'): channel={channel_real}, thread_ts={thread_ts_real}, permalink={fallback_permalink}")
        else:
            logger.error(f"process_ticket_command: Tidak menemukan fallback permalink pada thread_data_forward. thread_data_forward={thread_data_forward}")
            return
    if not channel_real or not thread_ts_real:
        logger.error(f"process_ticket_command: Gagal parsing channel/thread_ts dari parent_message atau fallback. parent_message={parent_forward}, thread_data_forward={thread_data_forward}")
        return
    # Ambil thread_data asli
    logger.info(f"process_ticket_command: WAJIB ambil thread_data dari thread asli: channel={channel_real}, thread_ts={thread_ts_real}")
    thread_data = slack_bot.get_thread_data(channel_real, thread_ts_real)
    parent = thread_data.get('parent_message', {}) if thread_data else {}
    channel_asli = channel  # simpan channel forward
    thread_ts_asli = thread_ts  # simpan thread_ts forward
    channel = channel_real
    thread_ts = thread_ts_real


    from spreadsheetbug import SpreadsheetBugManager
    sheet_name = os.getenv('BUG_SHEET_NAME', 'Bug List')
    if thread_data:
        parent_ts = parent.get('ts')
        from datetime import datetime
        dt = datetime.fromtimestamp(float(parent_ts)) if parent_ts else None
        reporting_date_time = dt.strftime('%Y-%m-%d %H:%M') if dt else ''
        analysis = gemini_analyzer.analyze_thread(thread_data) if thread_data else {}
        # Ambil nama reporter dari user pada parent message (link utama)
        reporter_name = 'Unknown'
        parent_user_id = parent.get('user')
        if parent_user_id:
            user_info = slack_bot.get_user_info(parent_user_id)
            if user_info:
                reporter_name = user_info.get('real_name', user_info.get('name', parent_user_id))
            else:
                reporter_name = parent_user_id
        else:
            # fallback ke hasil analisis jika ada
            reporter_name = analysis.get('reporter', 'Unknown')

        # Generate auto-increment code in format QR-001, QR-002, ...
        try:
            bug_manager = SpreadsheetBugManager()
            all_codes = []
            try:
                rows = bug_manager.get_all_bugs(sheet_name)
                if rows and len(rows) > 1:
                    header = rows[0]
                    try:
                        code_idx = header.index('Code')
                    except ValueError:
                        code_idx = None
                    if code_idx is not None:
                        for row in rows[1:]:
                            if len(row) > code_idx:
                                code_val = row[code_idx]
                                if code_val and isinstance(code_val, str) and code_val.startswith('QR-'):
                                    try:
                                        num = int(code_val.replace('QR-', '').lstrip('0') or '0')
                                        all_codes.append(num)
                                    except Exception:
                                        pass
            except Exception:
                pass
            next_code_num = (max(all_codes) if all_codes else 0) + 1
            code_str = f"QR-{next_code_num:03d}"
        except Exception:
            code_str = "QR-001"

        row_data = {
            'from': 'Eksternal',
            'type': analysis.get('type', ''),
            'code': code_str,
            'product': analysis.get('product', ''),
            'role': analysis.get('role', ''),
            'fitur': analysis.get('fitur', ''),
            'reporter': reporter_name,
            'reporting_date_time': reporting_date_time,
            'deskripsi': analysis.get('description', ''),
            'step reproduce': '',
            'severity': analysis.get('severity', ''),
            'urgency': analysis.get('urgency', ''),
            'assignee': '',
            'status': '',
            'scheduled release on': '',
            'link': permalink,
            'note': ''
        }
        try:
            is_new_row = bug_manager.prepend_row_bug(row_data, sheet_name)
            # Jika duplicate (is_new_row == False), skip update related ticket
            if is_new_row:
                # Tambahan: update kolom Related Ticket pada spreadsheet utama
                code_value = code_str
                link_message = permalink
                found = False
                for sheet in spreadsheet_manager.get_available_sheets():
                    links = [l.split('&cid=')[0] if l else l for l in spreadsheet_manager.get_all_links(sheet)]
                    if link_message in links:
                        updated = spreadsheet_manager.update_column_by_link(sheet, link_message, 'Related Ticket', code_value)
                        if updated:
                            logger.info(f"Berhasil update kolom Related Ticket pada sheet {sheet} untuk link {link_message} dengan value {code_value}")
                        else:
                            logger.error(f"Gagal update kolom Related Ticket pada sheet {sheet} untuk link {link_message}")
                        found = True
                        break
                if not found:
                    logger.info(f"Tidak ditemukan sheet yang mengandung link message {link_message} untuk update kolom Related Ticket")
                # Kirim response ke thread forward (bukan thread asli)
                slack_bot.send_message(channel_asli, f"✅ Ticketmu sudah tercatat di bug tracking dengan kode: {code_str}", thread_ts=thread_ts_asli)
            else:
                logger.info("Duplicate bug detected, skipping update of Related Ticket column.")
        except Exception as e:
            logger.error(f"Error mencatat bug: {str(e)}")
            slack_bot.send_message(channel, f"Gagal mencatat bug: {str(e)}", thread_ts=thread_ts)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'slack-thread-analyzer'})

def run_flask_app(port):
    """Run Flask app"""
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    # Untuk expose ke publik, jalankan: ngrok http 3000 di terminal lain
    run_flask_app(port)
