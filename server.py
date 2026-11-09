"""Wordle midterm FastAPI server.

Local: python -m uvicorn server:app --reload
Render: uvicorn server:app --host 0.0.0.0 --port $PORT
"""
import os
import random
import re
import uuid
from collections import Counter
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Wordle Midterm API", version="1.0")
MAX_ATTEMPTS = 6

# Same accepted five-letter dictionary as the instructor-provided starter.
WORD_BANK = [
    'APPLE', 'TRAIN', 'HOUSE', 'PLANT', 'SMART', 'WORLD', 'LIGHT', 'BRAIN', 'CLOUD', 'WATER',
    'ABOUT', 'ABOVE', 'ACTOR', 'ACUTE', 'ADMIT', 'ADOPT', 'ADULT', 'AFTER', 'AGAIN', 'AGENT',
    'AGREE', 'AHEAD', 'ALARM', 'ALBUM', 'ALERT', 'ALIEN', 'ALIKE', 'ALIVE', 'ALLOW', 'ALONE',
    'ALONG', 'ALTER', 'AMONG', 'ANGER', 'ANGLE', 'ANGRY', 'APART', 'APPLY', 'ARGUE', 'ARISE',
    'ARRAY', 'ARROW', 'ASIDE', 'ASSET', 'AUDIO', 'AUDIT', 'AVOID', 'AWAKE', 'AWARE', 'BADGE',
    'BAKER', 'BASIC', 'BASIS', 'BEACH', 'BEGIN', 'BEING', 'BELOW', 'BENCH', 'BLACK', 'BLAME',
    'BLANK', 'BLAST', 'BLEED', 'BLEND', 'BLOCK', 'BLOOD', 'BOARD', 'BOAST', 'BONUS', 'BOOST',
    'BOUND', 'BREAD', 'BREAK', 'BRICK', 'BRIEF', 'BRING', 'BROAD', 'BROWN', 'BRUSH', 'BUILD',
    'BUNCH', 'BUYER', 'CABLE', 'CANDY', 'CARGO', 'CARRY', 'CATCH', 'CAUSE', 'CHAIN', 'CHAIR',
    'CHALK', 'CHARM', 'CHART', 'CHASE', 'CHEAP', 'CHECK', 'CHEST', 'CHIEF', 'CHILD', 'CHOSE',
    'CIVIL', 'CLAIM', 'CLASS', 'CLEAN', 'CLEAR', 'CLIMB', 'CLOCK', 'CLOSE', 'COACH', 'COAST',
    'COUNT', 'COURT', 'COVER', 'CRASH', 'CREAM', 'CRIME', 'CROSS', 'CROWD', 'CROWN', 'CURVE',
    'CYCLE', 'DAILY', 'DANCE', 'DEATH', 'DELAY', 'DEPTH', 'DRAFT', 'DRAMA', 'DREAM', 'DRIVE',
    'EAGLE', 'EARLY', 'EARTH', 'EIGHT', 'EMPTY', 'ENEMY', 'ENJOY', 'ENTER', 'EQUAL', 'ERROR',
    'EVENT', 'EVERY', 'EXACT', 'EXIST', 'FAITH', 'FALSE', 'FAULT', 'FIELD', 'FIGHT', 'FINAL',
    'FIRST', 'FLAME', 'FLASH', 'FLOAT', 'FLOOR', 'FLOUR', 'FLUID', 'FOCUS', 'FORCE', 'FORTH',
    'FORTY', 'FORUM', 'FRAME', 'FRESH', 'FRONT', 'FRUIT', 'GIANT', 'GLASS', 'GLOBE', 'GRACE',
    'GRADE', 'GRAND', 'GRANT', 'GRASS', 'GREAT', 'GREEN', 'GROUP', 'GUARD', 'GUESS', 'GUIDE',
    'HAPPY', 'HEART', 'HEAVY', 'HOTEL', 'HUMAN', 'IMAGE', 'INDEX', 'INPUT', 'ISSUE', 'JUDGE',
    'KNIFE', 'LAYER', 'LEMON', 'LEVEL', 'LIMIT', 'LUNCH', 'MAGIC', 'MAJOR', 'MARCH', 'MATCH',
    'MEDAL', 'MONEY', 'MONTH', 'MUSIC', 'NIGHT', 'NOVEL', 'NURSE', 'OCEAN', 'OFFER', 'ORDER',
]
WORD_SET = set(WORD_BANK)
# The ten familiar words are used as answers; all WORD_BANK entries are valid guesses.
ANSWER_BANK = ["APPLE", "TRAIN", "HOUSE", "PLANT", "SMART",
               "WORLD", "LIGHT", "BRAIN", "CLOUD", "WATER"]

games_db: dict[str, dict[str, Any]] = {}
all_guess_words: list[str] = []
total_games = 0
wins = 0
lock = Lock()


class GuessRequest(BaseModel):
    game_id: str
    guess: str


def score_guess(guess: str, answer: str) -> list[str]:
    """Correctly score repeated letters: green first, then remaining yellows."""
    states = ["absent"] * 5
    remaining = Counter(answer)
    for i, letter in enumerate(guess):
        if letter == answer[i]:
            states[i] = "correct"
            remaining[letter] -= 1
    for i, letter in enumerate(guess):
        if states[i] == "absent" and remaining[letter] > 0:
            states[i] = "present"
            remaining[letter] -= 1
    return states


def enforce_hard_mode(history: list[dict[str, Any]], guess: str) -> None:
    """The exam requires known green letters at their revealed positions."""
    for previous in history:
        for pos, state in enumerate(previous["feedback"]):
            if state == "correct" and guess[pos] != previous["guess"][pos]:
                raise HTTPException(
                    status_code=400,
                    detail="Hard Mode: Must use revealed hint at green position",
                )


def get_stats() -> dict[str, Any]:
    return {
        "total_games": total_games,
        "wins": wins,
        "win_rate": round((wins / total_games) * 100, 1) if total_games else 0.0,
        "history_words": all_guess_words.copy(),
    }


@app.get("/")
def index() -> dict[str, str]:
    return {"message": "Wordle API is running", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with lock:
        return get_stats()


@app.post("/api/new-game")
def new_game(hard_mode: bool = False) -> dict[str, Any]:
    game_id = str(uuid.uuid4())
    with lock:
        games_db[game_id] = {
            "target": random.choice(ANSWER_BANK),
            "status": "PLAYING",
            "attempts": 0,
            "history": [],
            "hard_mode": hard_mode,
        }
        statistics = get_stats()
    return {"game_id": game_id, "hard_mode": hard_mode,
            "message": "New game started!", "stats": statistics}


@app.post("/api/guess")
def guess(req: GuessRequest) -> dict[str, Any]:
    global total_games, wins
    with lock:
        game = games_db.get(req.game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game session not found.")
        if game["status"] != "PLAYING":
            raise HTTPException(status_code=409, detail="Game over. Please start a new game.")

        # All validation happens BEFORE incrementing attempts or changing rows.
        if not re.fullmatch(r"[A-Za-z]{5}", req.guess):
            raise HTTPException(status_code=400, detail="Word must be 5 English letters.")
        word = req.guess.upper()
        if word not in WORD_SET:
            raise HTTPException(status_code=400, detail="Word not in dictionary")
        if game["hard_mode"]:
            enforce_hard_mode(game["history"], word)

        result = score_guess(word, game["target"])
        game["attempts"] += 1
        game["history"].append({"guess": word, "feedback": result})
        all_guess_words.append(word)
        is_correct = word == game["target"]
        if is_correct:
            game["status"] = "WON"
        elif game["attempts"] >= MAX_ATTEMPTS:
            game["status"] = "LOST"
        if game["status"] != "PLAYING":
            total_games += 1
            if is_correct:
                wins += 1
        statistics = get_stats()
        return {
            "guess": word,
            "feedback": result,
            "is_correct": is_correct,
            "status": game["status"],
            "attempts": game["attempts"],
            "remaining": MAX_ATTEMPTS - game["attempts"],
            "target_word": game["target"] if game["status"] != "PLAYING" else None,
            "hard_mode": game["hard_mode"],
            "stats": statistics,
            "history_words": statistics["history_words"],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
