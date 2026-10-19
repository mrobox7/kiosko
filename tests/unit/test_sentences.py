import asyncio
from typing import Any

import pytest

from app.llm.base import LLMResponse
from app.speech.fake import FakeStreamingTextToSpeech
from app.speech.sentences import SentenceFeed, SentenceSplitter
from tests.support.builders import make_session


def split(*pieces: str) -> list[str]:
    s = SentenceSplitter()
    out = [x for p in pieces for x in s.feed(p)]
    return out + s.finish()


def test_splits_at_full_stops_question_marks_and_exclamations() -> None:
    assert split("Hello Priya! How are you? Fine.") == ["Hello Priya!", "How are you?", "Fine."]


def test_a_sentence_is_held_until_the_next_word_proves_it_ended() -> None:
    s = SentenceSplitter()
    assert s.feed("Hello Priya!") == []  # "Hello Priya!!" or "Hello Priya!)" could follow
    assert s.feed(" How") == ["Hello Priya!"]
    assert s.finish() == ["How"]


def test_pieces_in_any_size_give_the_same_sentences() -> None:
    text = "Your table is booked. See you at 7:30 p.m. tonight! Anything else?"
    assert (
        split(*text)
        == split(text)
        == [
            "Your table is booked.",
            "See you at 7:30 p.m. tonight!",
            "Anything else?",
        ]
    )


def test_does_not_split_inside_numbers_times_and_abbreviations() -> None:
    assert split("It costs 3.5 rupees.") == ["It costs 3.5 rupees."]
    assert split("Mr. Rao booked at 8 p.m. today. Rs. 400 each.") == [
        "Mr. Rao booked at 8 p.m. today.",
        "Rs. 400 each.",
    ]


def test_hindi_full_stop_and_mixed_punctuation() -> None:
    assert split("नमस्ते। आप कैसे हैं?") == ["नमस्ते।", "आप कैसे हैं?"]
    assert split("Really?! Yes.") == ["Really?!", "Yes."]


def test_a_new_line_ends_a_sentence() -> None:
    assert split("First line\nSecond line") == ["First line", "Second line"]


def test_a_very_long_run_without_a_full_stop_is_cut_at_a_space() -> None:
    s = SentenceSplitter(max_chars=20)
    out = s.feed("one two three four five six seven")
    assert out and all(len(x) <= 20 for x in out) and "".join(out + s.finish()).replace(" ", "")


def test_ellipsis_inside_real_words_is_not_junk() -> None:
    assert split("Hmm... let me check. One moment.") == ["Hmm...", "let me check.", "One moment."]


def test_a_flood_of_dots_is_dropped_then_stops_the_reply() -> None:
    s = SentenceSplitter()
    out = s.feed("Done.\n" + "...\n" * 3 + "Okay\n" + "...\n" * 5)
    assert out == ["Done.", "Okay"] and s.runaway
    assert s.feed("This is never spoken.\n") == [] and s.finish() == []


def test_a_few_stray_dots_are_dropped_but_the_reply_goes_on() -> None:
    s = SentenceSplitter()
    assert split("Fine.\n...\nGreat.") == ["Fine.", "Great."]
    assert not s.runaway


def test_the_same_sentence_three_times_stops_the_reply() -> None:
    s = SentenceSplitter()
    out = s.feed("Sorry. Sorry! sorry... Sorry. Sorry. ")
    assert out == ["Sorry.", "Sorry!"] and s.runaway


def test_a_sentence_said_twice_is_allowed() -> None:
    assert split("No. No. Yes.") == ["No.", "No.", "Yes."]


def run(coro: Any) -> Any:
    return asyncio.run(asyncio.wait_for(coro, 5))


def test_the_feed_hands_sentences_from_a_thread_to_the_event_loop() -> None:
    async def go() -> list[str]:
        feed = SentenceFeed(asyncio.get_running_loop())

        def model_thread() -> None:
            for piece in ["Booked. See ", "you soon. Bye"]:
                feed.push(piece)
            feed.close()

        task = asyncio.create_task(asyncio.to_thread(model_thread))
        out = [s async for s in feed]
        await task
        return out

    assert run(go()) == ["Booked.", "See you soon.", "Bye"]


def test_a_runaway_reply_ends_the_stream_and_is_flagged() -> None:
    async def go() -> tuple[list[str], bool]:
        feed = SentenceFeed(asyncio.get_running_loop())
        for piece in ["Fine.\n", "...\n" * 8, "never spoken.\n"]:
            feed.push(piece)
        return [s async for s in feed], feed.runaway

    assert run(go()) == (["Fine."], True)


def test_session_to_speech_end_to_end_with_fakes() -> None:
    session, _, _ = make_session([LLMResponse(text="Booked for tonight. See you then!")])
    speaker = FakeStreamingTextToSpeech()

    async def go() -> list[bytes]:
        feed = SentenceFeed(asyncio.get_running_loop())

        def turn() -> None:
            try:
                session.send("book me", spoken=True, on_text=feed.push)
            finally:
                feed.close()

        task = asyncio.create_task(asyncio.to_thread(turn))
        clips = [c.data async for c in speaker.stream(feed, language="en-IN")]
        await task
        return clips

    assert run(go()) == [b"Booked for tonight.", b"See you then!"]
    assert speaker.spoken == ["Booked for tonight.", "See you then!"]


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_nothing_to_say_gives_no_sentences(text: str) -> None:
    assert split(text) == []
