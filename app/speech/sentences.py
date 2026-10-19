"""From the model's text pieces to whole sentences a voice can speak.

`SentenceSplitter` cuts the pieces into sentences and stops a reply that has run away (a flood of
"..." or the same sentence over and over). `SentenceFeed` hands those sentences from the thread
that runs the model to the async side that speaks them."""

import asyncio
import re

TERMINATORS = ".?!।"  # । is the Hindi full stop
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "rs.", "st."}
INITIALISMS = re.compile(r"(?:^|\s)(?:[A-Za-z]\.)+$")  # a.m. p.m. e.g. i.e.
MAX_SENTENCE_CHARS = 400  # Sarvam advises under 500 per message for streaming
JUNK_LIMIT = 6  # sentences with no letters or digits, in one reply
REPEAT_LIMIT = 3  # the same sentence this many times in a row


class SentenceSplitter:
    """Feed text pieces, get finished sentences. One instance per reply, used from one thread.
    After `runaway` turns True nothing more is returned."""

    def __init__(self, max_chars: int = MAX_SENTENCE_CHARS) -> None:
        self._max_chars = max_chars
        self._buffer = ""
        self._junk = 0
        self._last = ""
        self._repeats = 0
        self.runaway = False

    def feed(self, piece: str) -> list[str]:
        """Add a piece; return the sentences it completed."""
        if self.runaway:
            return []
        self._buffer += piece
        out: list[str] = []
        while (cut := self._boundary()) is not None:
            out += self._accept(self._buffer[:cut])
            self._buffer = self._buffer[cut:]
            if self.runaway:
                self._buffer = ""
                return out
        return out

    def finish(self) -> list[str]:
        """The reply is over: return what is left as a last sentence."""
        rest, self._buffer = self._buffer, ""
        return [] if self.runaway else self._accept(rest)

    def _boundary(self) -> int | None:
        """Where the first finished sentence in the buffer ends, if there is one."""
        text = self._buffer
        for i, char in enumerate(text):
            if char == "\n":
                return i + 1
            if char in TERMINATORS and i + 1 < len(text) and text[i + 1].isspace():
                if not (char == "." and _is_abbreviation(text[: i + 1])):
                    return i + 1
        if len(text) > self._max_chars:
            space = text.rfind(" ", 0, self._max_chars)
            return space + 1 if space > 0 else self._max_chars
        return None

    def _accept(self, raw: str) -> list[str]:
        text = raw.strip()
        if not text:
            return []
        if not any(c.isalnum() for c in text):
            self._junk += 1
            self.runaway = self._junk >= JUNK_LIMIT
            return []
        key = re.sub(r"\W+", " ", text.lower()).strip()
        self._repeats = self._repeats + 1 if key == self._last else 1
        self._last = key
        if self._repeats >= REPEAT_LIMIT:
            self.runaway = True
            return []
        return [text]


def _is_abbreviation(upto_period: str) -> bool:
    words = upto_period.split()
    return bool(words) and (
        words[-1].lower() in ABBREVIATIONS or INITIALISMS.search(upto_period) is not None
    )


class SentenceFeed:
    """Sentences from the thread running the model to the task that speaks them.
    `push` and `close` are called from the model's thread; iterate it in the event loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._splitter = SentenceSplitter()
        self._closed = False

    @property
    def runaway(self) -> bool:
        """True if the reply was cut off because it ran away."""
        return self._splitter.runaway

    def push(self, piece: str) -> None:
        """A piece of reply text from the model. Ignored once closed or run away."""
        if self._closed:
            return
        for sentence in self._splitter.feed(piece):
            self._put(sentence)
        if self._splitter.runaway:
            self.close()

    def close(self) -> None:
        """The reply is over (or was stopped): speak what is left, then end the stream."""
        if self._closed:
            return
        for sentence in self._splitter.finish():
            self._put(sentence)
        self._closed = True
        self._put(None)

    def _put(self, item: str | None) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def __aiter__(self) -> SentenceFeed:
        return self

    async def __anext__(self) -> str:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item
