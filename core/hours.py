"""Business hours and local time (Dearborn, MI)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Detroit")

# Monday = 0
HOURS = {
    0: (time(7, 0), time(19, 0)),
    1: (time(7, 0), time(19, 0)),
    2: (time(7, 0), time(17, 0)),
    3: (time(7, 0), time(19, 0)),
    4: (time(7, 0), time(22, 0)),
    5: (time(10, 0), time(22, 0)),
    6: (time(10, 0), time(22, 0)),
}
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def now():
    """Current local time as a naive datetime (all stored times are local)."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def today():
    return now().date()


def hours_for(day: date):
    open_t, close_t = HOURS[day.weekday()]
    return datetime.combine(day, open_t), datetime.combine(day, close_t)


def is_open(at=None):
    at = at or now()
    o, c = hours_for(at.date())
    return o <= at < c


def fmt_time(t):
    return t.strftime("%I:%M %p").lstrip("0")


def parse(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def iso(dt):
    return dt.replace(microsecond=0).isoformat(sep=" ") if dt else None


def fmt_dt(dt):
    dt = parse(dt)
    if dt is None:
        return ""
    if dt.date() == today():
        return f"Today {fmt_time(dt)}"
    if dt.date() == today() + timedelta(days=1):
        return f"Tomorrow {fmt_time(dt)}"
    return dt.strftime("%a %b %d, ") + fmt_time(dt)


def next_opening(at=None):
    at = at or now()
    for i in range(0, 8):
        d = at.date() + timedelta(days=i)
        o, _ = hours_for(d)
        if at < o:
            return o
    return None


def status_line(at=None):
    at = at or now()
    o, c = hours_for(at.date())
    if o <= at < c:
        mins = int((c - at).total_seconds() // 60)
        extra = " Closing soon." if mins <= 30 else ""
        return True, f"Open now until {fmt_time(c)}.{extra}"
    nxt = next_opening(at)
    if nxt.date() == at.date():
        when = "today"
    elif nxt.date() == at.date() + timedelta(days=1):
        when = "tomorrow"
    else:
        when = DAY_NAMES[nxt.weekday()]
    return False, f"Closed. Opens {when} at {fmt_time(nxt)}."


def ceil_to(dt, minutes):
    """Round a datetime up to the next multiple of `minutes`."""
    dt = dt.replace(second=0, microsecond=0)
    rem = dt.minute % minutes
    if rem:
        dt += timedelta(minutes=minutes - rem)
    return dt


def day_label(d):
    if d == today():
        return "Today"
    if d == today() + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%a %b %d")
