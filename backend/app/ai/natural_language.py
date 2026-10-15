"""Small deterministic Indonesian date/time parser for no-key and clarification paths."""
from datetime import datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

WEEKDAYS = {
    "senin": 0,
    "selasa": 1,
    "rabu": 2,
    "kamis": 3,
    "jumat": 4,
    "jum'at": 4,
    "sabtu": 5,
    "minggu": 6,
}
MONTHS = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}

_TIME_RE = re.compile(
    r"\b(?:jam|pukul)\s*(\d{1,2})(?:[:.](\d{2}))?\b"
    r"|\b(\d{1,2})[:.](\d{2})\b",
    re.IGNORECASE,
)


def parse_datetime(
    text: str,
    timezone_name: str,
    *,
    require_time: bool = True,
    require_date: bool = False,
    default_time: time | None = None,
    reference: datetime | None = None,
) -> datetime | None:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("Asia/Jakarta")
    now = reference.astimezone(zone) if reference else datetime.now(zone)
    lowered = text.lower()

    time_match = _TIME_RE.search(lowered)
    parsed_time: time | None = None
    if time_match:
        hour = int(time_match.group(1) or time_match.group(3))
        minute = int(time_match.group(2) or time_match.group(4) or "0")
        if hour > 23 or minute > 59:
            return None
        period = re.search(r"\b(pagi|siang|sore|malam)\b", lowered)
        if period and hour <= 12:
            if period.group(1) == "pagi" and hour == 12:
                hour = 0
            elif period.group(1) == "siang" and 1 <= hour <= 11:
                hour += 12
            elif period.group(1) == "sore" and 1 <= hour <= 11:
                hour += 12
            elif period.group(1) == "malam" and 1 <= hour <= 11:
                hour += 12
        parsed_time = time(hour, minute)
    elif default_time is not None:
        parsed_time = default_time
    elif require_time:
        return None

    target_date = now.date()
    explicit_date = False
    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lowered)
    if iso_match:
        try:
            target_date = datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            ).date()
        except ValueError:
            return None
        explicit_date = True
    elif re.search(r"\b(lusa|day after tomorrow)\b", lowered):
        target_date = now.date() + timedelta(days=2)
        explicit_date = True
    elif re.search(r"\b(besok|esok|tomorrow)\b", lowered):
        target_date = now.date() + timedelta(days=1)
        explicit_date = True
    elif re.search(r"\b(hari ini|today)\b", lowered):
        target_date = now.date()
        explicit_date = True
    else:
        day_match = re.search(r"\b(?:tanggal|tgl)\s*(\d{1,2})(?:\s+([a-z]+))?", lowered)
        month_day_match = re.search(
            r"\b(\d{1,2})\s+(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\b",
            lowered,
        )
        if day_match or month_day_match:
            day = int((day_match or month_day_match).group(1))
            month_name = (day_match.group(2) if day_match else month_day_match.group(2))
            month = MONTHS.get(month_name) if month_name else now.month
            year = now.year
            try:
                candidate = now.date().replace(year=year, month=month, day=day)
            except ValueError:
                return None
            if candidate < now.date():
                if month_name:
                    year += 1
                else:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                try:
                    candidate = candidate.replace(year=year, month=month)
                except ValueError:
                    return None
            target_date = candidate
            explicit_date = True
        else:
            weekday_match = re.search(
                r"\b(senin|selasa|rabu|kamis|jum['’]?at|sabtu|minggu)\b",
                lowered,
            )
            if weekday_match:
                weekday = WEEKDAYS[weekday_match.group(1).replace("’", "'")]
                delta = (weekday - now.weekday()) % 7
                if delta == 0:
                    delta = 7
                if re.search(r"\b(minggu depan|pekan depan|minggu berikutnya|next week)\b", lowered):
                    delta += 7
                target_date = now.date() + timedelta(days=delta)
                explicit_date = True
            elif re.search(r"\b(minggu depan|pekan depan|next week)\b", lowered):
                target_date = now.date() + timedelta(days=7)
                explicit_date = True

    if require_date and not explicit_date:
        return None
    if parsed_time is None:
        parsed_time = time(0, 0)
    result = datetime.combine(target_date, parsed_time, tzinfo=zone)
    if explicit_date and require_time and result <= now:
        return None
    if not explicit_date and result <= now:
        result += timedelta(days=1)
    return result


def extract_title(text: str) -> str:
    title = text.lower()
    title = _TIME_RE.sub(" ", title)
    title = re.sub(r"\b(?:tanggal|tgl)\s*\d{1,2}(?:\s+[a-z]+)?\b", " ", title)
    title = re.sub(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", " ", title)
    for word in sorted((*WEEKDAYS.keys(), *MONTHS.keys()), key=len, reverse=True):
        title = re.sub(rf"\b{re.escape(word)}\b", " ", title)
    title = re.sub(
        r"\b(hari ini|besok|esok|lusa|minggu depan|pekan depan|setiap|tiap|"
        r"jam|pukul|pagi|siang|sore|malam|aku|saya|gue|gua|gw|kamu|"
        r"ingatkan|ingetin|ingat|inget|remind|reminder|pengingat|memory|memori|ingatan|"
        r"ada|mau|akan|harus|tolong|buat|catat|jadwalkan|dalam|untuk|"
        r"sebelum|pada|ke|di|yang|sudah|deadline|task|tugas|todo|to-do)\b",
        " ",
        title,
    )
    title = re.sub(r"\s+", " ", title).strip(" ,.!?;:")
    return title[:255] or "Aktivitas"


def event_category(text: str) -> str:
    lowered = text.lower()
    categories = (
        ("ACADEMIC", ("kuliah", "kelas", "ujian", "kampus")),
        ("MEETING", ("meeting", "rapat", "organisasi")),
        ("WORK", ("kantor", "kerja", "klien")),
        ("SOCIAL", ("teman", "nongkrong", "hangout")),
        ("STUDY", ("belajar", "study")),
        ("HEALTH", ("gym", "olahraga", "dokter", "periksa")),
        ("TRAVEL", ("perjalanan", "berangkat", "surabaya", "travel")),
    )
    for category, keywords in categories:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "OTHER"


def extract_recurrence(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\b(setiap hari|tiap hari|setiap malam|setiap pagi)\b", lowered):
        return "DAILY"
    if re.search(r"\b(setiap|tiap)\b", lowered):
        for weekday, _ in sorted(WEEKDAYS.items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"\b{re.escape(weekday)}\b", lowered):
                return f"WEEKLY:{WEEKDAYS[weekday]}"
    return None
