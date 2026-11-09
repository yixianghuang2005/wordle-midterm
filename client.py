"""700x700 Wordle desktop client for the FastAPI midterm project.

After Render deployment, replace the localhost fallback URL with your LIVE HTTPS
service URL, or set the WORDLE_API_URL environment variable before launching.
"""
import os
import queue
import threading

import pygame
import requests

API_BASE_URL = os.environ.get("WORDLE_API_URL", "https://wordle-midterm-nil5.onrender.com").rstrip("/")
WIDTH, HEIGHT = 700, 700
BG = (18, 18, 19)
PANEL = (27, 29, 32)
WHITE = (245, 246, 247)
MUTED = (164, 169, 175)
BORDER = (62, 65, 68)
KEY_BG = (113, 117, 122)
GREEN = (83, 141, 78)
YELLOW = (181, 159, 59)
RED = (220, 112, 104)
BLUE = (72, 111, 172)
COLORS = {"correct": GREEN, "present": YELLOW, "absent": BORDER}
RANK = {"correct": 3, "present": 2, "absent": 1}
LEFT_RIGHT = 499
RIGHT_X = 507
RIGHT_W = 183
BOARD_X = 106
BOARD_Y = 107
TILE = 52
TILE_GAP = 7
KEY_START_Y = 517
KEY_H = 42
KEY_GAP_Y = 52
HISTORY_TOP = 332
HISTORY_BOTTOM = 657


def font(name, size, bold=False):
    return pygame.font.SysFont(name, size, bold=bold)


class WordleGame:
    def __init__(self):
        self.title_font = font("arial", 37, True)
        self.tile_font = font("arial", 31, True)
        self.body_font = font("arial", 17)
        self.medium_font = font("arial", 15)
        self.small_font = font("arial", 13)
        self.key_font = font("arial", 15, True)
        self.stat_font = font("arial", 19, True)
        self.results = queue.Queue()
        self.busy = False
        self.game_id = None
        self.hard_mode = False
        self.rows = []
        self.current = ""
        self.key_colors = {}
        self.game_over = False
        self.message = "Connecting to server..."
        self.total, self.wins, self.rate = 0, 0, 0.0
        self.history_words = []
        self.history_scroll = 0
        self.keys = []
        self.mode_rect = pygame.Rect(518, 56, 160, 42)
        self.restart_rect = pygame.Rect(518, 107, 160, 40)
        self.history_rect = pygame.Rect(514, HISTORY_TOP, 170, HISTORY_BOTTOM - HISTORY_TOP)
        self.setup_keys()
        pygame.key.stop_text_input()
        self.new_game()

    def setup_keys(self):
        rows = [list("QWERTYUIOP"), list("ASDFGHJKL"),
                ["ENTER", *list("ZXCVBNM"), "DEL"]]
        for ri, letters in enumerate(rows):
            widths = [58 if len(ch) > 1 else 42 for ch in letters]
            gap = 4
            span = sum(widths) + gap * (len(letters) - 1)
            x = (LEFT_RIGHT - span) // 2
            for label, w in zip(letters, widths):
                rect = pygame.Rect(x, KEY_START_Y + ri * KEY_GAP_Y, w, KEY_H)
                self.keys.append((rect, label))
                x += w + gap

    def send(self, kind, path, payload=None):
        if self.busy:
            return
        self.busy = True
        self.message = "Contacting server..."

        def work():
            try:
                response = requests.post(API_BASE_URL + path, json=payload, timeout=(10, 100))
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                if not response.ok:
                    detail = body.get("detail", f"HTTP {response.status_code}")
                    if response.status_code == 400 and detail == "Word not in dictionary":
                        detail = "Not in word list!"
                    self.results.put((kind, None, str(detail)))
                else:
                    self.results.put((kind, body, None))
            except requests.RequestException as exc:
                self.results.put((kind, None, "Network error: " + type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def new_game(self):
        self.send("new", "/api/new-game?hard_mode=" + str(self.hard_mode).lower(), {})

    def read_response(self):
        try:
            kind, data, error = self.results.get_nowait()
        except queue.Empty:
            return
        self.busy = False
        if error:
            self.message = error
            return  # An invalid guess leaves the row and attempt untouched.
        if kind == "new":
            self.game_id = data["game_id"]
            self.rows = []
            self.current = ""
            self.key_colors = {}
            self.game_over = False
            self.message = "New game! Enter a five-letter word."
        elif kind == "guess":
            self.rows.append(data)
            self.current = ""
            for letter, state in zip(data["guess"], data["feedback"]):
                if RANK[state] > RANK.get(self.key_colors.get(letter), 0):
                    self.key_colors[letter] = state
            self.game_over = data["status"] != "PLAYING"
            if data["status"] == "WON":
                self.message = "Congratulations! You won! Press R to restart."
            elif data["status"] == "LOST":
                self.message = f'Game Over! The word was {data["target_word"]}. Press R to restart.'
            else:
                self.message = f'Keep guessing! ({data["remaining"]} tries left!)'
        stats = data.get("stats", {})
        self.total = stats.get("total_games", self.total)
        self.wins = stats.get("wins", self.wins)
        self.rate = stats.get("win_rate", self.rate)
        old_n = len(self.history_words)
        self.history_words = stats.get("history_words", self.history_words)
        if len(self.history_words) != old_n:
            self.history_scroll = 0  # 0 = show the most recent valid guesses

    def press(self, key):
        if self.busy:
            return
        if key == "F2":
            self.new_game()
            return
        if key == "TOGGLE_HARD":
            self.hard_mode = not self.hard_mode
            self.new_game()  # the server locks the chosen mode per game
            return
        if key == "R" and self.game_over:
            self.new_game()
            return
        if self.game_over or not self.game_id:
            return
        if key == "DEL":
            self.current = self.current[:-1]
        elif key == "ENTER":
            if len(self.current) != 5:
                self.message = "Not enough letters!"
            else:
                self.send("guess", "/api/guess", {"game_id": self.game_id, "guess": self.current})
        elif len(key) == 1 and key in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if len(self.current) < 5:
                self.current += key

    def event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_F2:
                self.press("F2")
            elif e.key == pygame.K_F1:
                self.press("TOGGLE_HARD")
            elif e.key == pygame.K_h:
                if e.mod & pygame.KMOD_SHIFT:  # Shift+H enters the letter H.
                    self.press("H")
                else:
                    self.press("TOGGLE_HARD")
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.press("ENTER")
            elif e.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                self.press("DEL")
            elif not e.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META):
                if pygame.K_a <= e.key <= pygame.K_z:
                    self.press(chr(ord("A") + e.key - pygame.K_a))
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.mode_rect.collidepoint(e.pos):
                self.press("TOGGLE_HARD")
            elif self.restart_rect.collidepoint(e.pos):
                self.press("F2")
            else:
                for rect, name in self.keys:
                    if rect.collidepoint(e.pos):
                        self.press(name)
                        break
        elif e.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self.history_rect.collidepoint((mx, my)):
                max_scroll = max(0, len(self.history_words) - 15)
                self.history_scroll = max(0, min(max_scroll, self.history_scroll + e.y))

    @staticmethod
    def text(surface, fnt, text, center, color=WHITE):
        image = fnt.render(str(text), True, color)
        surface.blit(image, image.get_rect(center=center))

    def panel(self, surface):
        pygame.draw.rect(surface, PANEL, (RIGHT_X, 12, RIGHT_W, 676), border_radius=10)
        self.text(surface, self.medium_font, "CONTROL", (598, 34), MUTED)
        pygame.draw.rect(surface, BLUE if self.hard_mode else BORDER, self.mode_rect, border_radius=6)
        self.text(surface, self.body_font, "Mode: HARD" if self.hard_mode else "Mode: Normal", self.mode_rect.center)
        pygame.draw.rect(surface, BORDER, self.restart_rect, border_radius=6)
        self.text(surface, self.body_font, "F2: New Game", self.restart_rect.center)
        pygame.draw.line(surface, BORDER, (516, 161), (680, 161))
        self.text(surface, self.medium_font, "GAME STATS", (597, 179), MUTED)
        for label, number, yy in (("Total", self.total, 206), ("Wins", self.wins, 232),
                                  ("Win Rate", f"{self.rate:.1f}%", 258)):
            surface.blit(self.medium_font.render(label, True, MUTED), (519, yy - 9))
            value_img = self.stat_font.render(str(number), True, WHITE)
            surface.blit(value_img, (677 - value_img.get_width(), yy - 11))
        pygame.draw.line(surface, BORDER, (516, 280), (680, 280))
        self.text(surface, self.medium_font, "WORD HISTORY", (596, 302), MUTED)
        self.text(surface, self.small_font, f"{len(self.history_words)} valid guesses", (596, 323), MUTED)
        surface.set_clip(self.history_rect)
        visible_count = 15
        n = len(self.history_words)
        stop = max(0, n - self.history_scroll)
        start = max(0, stop - visible_count)
        shown = self.history_words[start:stop]
        if not shown:
            self.text(surface, self.medium_font, "No guesses yet", (600, 357), MUTED)
        for index, word in enumerate(shown):
            y = HISTORY_TOP + 7 + index * 21
            if index % 2 == 0:
                pygame.draw.rect(surface, (35, 37, 40), (517, y - 2, 159, 20), border_radius=2)
            surface.blit(self.small_font.render(f"{start+index+1:02d}", True, MUTED), (521, y))
            surface.blit(self.medium_font.render(word, True, WHITE), (560, y-1))
        surface.set_clip(None)
        self.text(surface, self.small_font, "Wheel: scroll history", (597, 675), MUTED)

    def board(self, surface):
        self.text(surface, self.title_font, "WORDLE", (247, 37))
        self.text(surface, self.small_font, "FASTAPI  +  PYGAME", (248, 78), MUTED)
        for r in range(6):
            result = self.rows[r] if r < len(self.rows) else None
            word = result["guess"] if result else (self.current if r == len(self.rows) else "")
            for c in range(5):
                rect = pygame.Rect(BOARD_X + c * (TILE + TILE_GAP),
                                   BOARD_Y + r * (TILE + TILE_GAP), TILE, TILE)
                state = result["feedback"][c] if result else None
                if state:
                    pygame.draw.rect(surface, COLORS[state], rect, border_radius=4)
                else:
                    focus = (r == len(self.rows) and c == len(self.current)
                             and not self.busy and not self.game_over)
                    pygame.draw.rect(surface, WHITE if focus else BORDER, rect,
                                     width=2, border_radius=4)
                if c < len(word):
                    self.text(surface, self.tile_font, word[c], rect.center)

        # Messages and help have separate, non-overlapping bands.
        pygame.draw.line(surface, BORDER, (26, 458), (473, 458))
        msg = self.message
        text_size = self.medium_font.size(msg)[0]
        fnt = self.medium_font if text_size <= 455 else self.small_font
        if fnt.size(msg)[0] > 455:
            while msg and fnt.size(msg + "...")[0] > 455:
                msg = msg[:-1]
            msg += "..."
        self.text(surface, fnt, msg, (249, 477), RED if "error" in msg.lower() else WHITE)
        self.text(surface, self.small_font,
                  "H: Hard Mode  |  Shift+H: type H  |  F2: New Game",
                  (249, 501), MUTED)
        for rect, key in self.keys:
            clr = COLORS.get(self.key_colors.get(key), KEY_BG)
            pygame.draw.rect(surface, clr, rect, border_radius=5)
            self.text(surface, self.key_font, key, rect.center)
        self.text(surface, self.small_font,
                  "Enter: submit   |   Backspace: delete   |   Click keys to type",
                  (249, 684), MUTED)

    def draw(self, surface):
        surface.fill(BG)
        self.board(surface)
        self.panel(surface)


def main():
    pygame.init()
    pygame.key.stop_text_input()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Wordle Midterm — 700x700")
    clock = pygame.time.Clock()
    game = WordleGame()
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            else:
                game.event(e)
        game.read_response()
        game.draw(screen)
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    main()
