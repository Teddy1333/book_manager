def normalize_isbn(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isdigit() or ch == "X")


def pages_as_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def log_lookup_warning(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))
