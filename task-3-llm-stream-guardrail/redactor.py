import re


EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}"
    r"@"
    r"[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9-])"
)

SSN_PATTERN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

PII_PATTERNS = (EMAIL_PATTERN, SSN_PATTERN, CARD_PATTERN)
MAX_EMAIL_CHARACTERS = 382
NUMBER_OVERLAP_CHARACTERS = 40
REDACTION = "[REDACTED]"


def redact_pii(text: str) -> str:
    for pattern in PII_PATTERNS:
        text = pattern.sub(REDACTION, text)
    return text


class StreamingPIIRedactor:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> str:
        self._buffer += text

        # Keep enough trailing text to catch a card number split across chunks.
        safe_cut = len(self._buffer) - NUMBER_OVERLAP_CHARACTERS
        if safe_cut <= 0:
            return ""

        # Don't split the current word: a partial email may be in it.
        suffix = self._buffer[:safe_cut]
        token = re.search(r"\S*$", suffix)
        token_start = token.start() if token else safe_cut
        token_length = safe_cut - token_start

        if token_length <= MAX_EMAIL_CHARACTERS:
            safe_cut = token_start
        else:
            # Even a long unbroken string can contain a complete email.
            safe_cut = min(
                safe_cut,
                len(self._buffer) - MAX_EMAIL_CHARACTERS,
            )

        # If a recognized PII value crosses the cut, keep the whole value
        # buffered so its first part can't leak.
        moved_cut = True
        while moved_cut:
            moved_cut = False
            for pattern in PII_PATTERNS:
                for match in pattern.finditer(self._buffer):
                    if match.start() < safe_cut < match.end():
                        safe_cut = match.start()
                        moved_cut = True

        safe_text = self._buffer[:safe_cut]
        self._buffer = self._buffer[safe_cut:]
        return redact_pii(safe_text)

    def finish(self) -> str:
        remaining_text = redact_pii(self._buffer)
        self._buffer = ""
        return remaining_text