from django import template

register = template.Library()

@register.filter(name='format_duration')
def format_duration(seconds):
    """
    Formats seconds into human readable duration string:
    - Below 60s: e.g. "45s"
    - Above 60s (under 60m): "minutes:secs" e.g. "2m:05s"
    - Above 60m (under 24h): "hours:minutes:secs" e.g. "1h:02m:05s"
    - Above 24h: "days:hours:minutes:secs" e.g. "1d:01h:02m:05s"
    """
    if seconds is None or seconds == '':
        return "-"
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "-"

    if seconds < 0:
        return "0s"

    days = seconds // 86400
    remainder = seconds % 86400
    hours = remainder // 3600
    remainder = remainder % 3600
    minutes = remainder // 60
    secs = remainder % 60

    if days > 0:
        return f"{days}d:{hours:02d}h:{minutes:02d}m:{secs:02d}s"
    elif hours > 0:
        return f"{hours}h:{minutes:02d}m:{secs:02d}s"
    elif minutes > 0:
        return f"{minutes}m:{secs:02d}s"
    else:
        return f"{secs}s"
