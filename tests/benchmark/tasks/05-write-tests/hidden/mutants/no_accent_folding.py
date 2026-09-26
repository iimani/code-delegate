import re
import unicodedata
from typing import Optional


def slugify(text: str, max_length: Optional[int] = None) -> str:
    """Turn arbitrary text into a URL slug.

    Rules, applied in order:
      1. Accented characters are reduced to their ASCII base letter
         ("Crème" -> "creme"); other non-ASCII characters are dropped.
      2. The result is lower-cased.
      3. Every run of characters that are not ASCII letters or digits becomes
         a single "-".
      4. Leading and trailing "-" are removed.
      5. If ``max_length`` is given, the slug is cut to at most that many
         characters, and any "-" left at the end by the cut is removed.

    >>> slugify("  Hello, World!  ")
    'hello-world'
    """
    normalized = text
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if max_length is not None:
        slug = slug[:max_length].rstrip("-")
    return slug
