# display.py

import pygame
import json
import time
import math
import random
import sys
from questions import QUESTIONS

import serial
import threading

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────
DATA_PATH       = "data.json"
SCORES_PATH     = "scores.json"
POLL_INTERVAL   = 0.5       # seconds between JSON reads
RESULT_DURATION = 5.0       # seconds to show results before next question
VOTE_THRESHOLD  = 1         # minimum total votes before showing results
FPS             = 60

# Fonts (bundled with Raspberry Pi OS / most Linux)
FONT_PATH       = None      # None = pygame default; swap for a TTF path if you have one

# Left card colours  (top, bottom)
LEFT_GRAD  = [(255, 60,  80),  (255, 140, 0)]
# Right card colours (top, bottom)
RIGHT_GRAD = [(30,  160, 255), (80,  60, 255)]

# After voting: greyed-out winner side becomes dark, loser keeps colour
GREY_TOP   = (70,  70,  80)
GREY_BOT   = (50,  50,  60)

#link data from arduino
SERIAL_PORT = "/dev/ttyACM0"  # change to ttyUSB0 if needed
SERIAL_BAUD = 115200


# ─────────────────────────────────────────────
#  Gradient helpers
# ─────────────────────────────────────────────
def draw_gradient_rect(surface, rect, color_top, color_bot):
    """Draw a vertical gradient in rect."""
    x, y, w, h = rect
    for row in range(h):
        t = row / max(h - 1, 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        pygame.draw.line(surface, (r, g, b), (x, y + row), (x + w, y + row))


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


# ─────────────────────────────────────────────
#  Text helpers
# ─────────────────────────────────────────────
def render_wrapped(surface, text, font, color, rect, center=True):
    """Word-wrap text inside rect and blit it."""
    words = text.split()
    lines, line = [], []
    for word in words:
        test = " ".join(line + [word])
        if font.size(test)[0] <= rect.width - 40:
            line.append(word)
        else:
            if line:
                lines.append(" ".join(line))
            line = [word]
    if line:
        lines.append(" ".join(line))

    line_height = font.get_linesize()
    total_h = line_height * len(lines)
    start_y = rect.y + (rect.height - total_h) // 2 if center else rect.y + 20

    for i, ln in enumerate(lines):
        surf = font.render(ln, True, color)
        x = rect.x + (rect.width - surf.get_width()) // 2 if center else rect.x + 20
        surface.blit(surf, (x, start_y + i * line_height))


# ─────────────────────────────────────────────
#  Particle system (subtle floating dots)
# ─────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, side_w, screen_h):
        self.x = x
        self.y = y
        self.vy = -random.uniform(0.3, 1.0)
        self.vx = random.uniform(-0.3, 0.3)
        self.alpha = random.randint(30, 90)
        self.radius = random.randint(2, 5)
        self.side_w = side_w
        self.screen_h = screen_h

    def update(self):
        self.x += self.vx
        self.y += self.vy

    def is_alive(self):
        return self.y + self.radius > 0

    def draw(self, surface):
        s = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, self.alpha), (self.radius, self.radius), self.radius)
        surface.blit(s, (int(self.x - self.radius), int(self.y - self.radius)))


# ─────────────────────────────────────────────
#  Main display class
# ─────────────────────────────────────────────
class WouldYouRatherDisplay:
    def __init__(self, reset_counts_callback=None):
        pygame.init()
        info = pygame.display.Info()
        self.W, self.H = info.current_w, info.current_h
        self.screen = pygame.display.set_mode((self.W, self.H), pygame.FULLSCREEN)
        pygame.display.set_caption("Would You Rather")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.reset_counts_callback = reset_counts_callback

        # Fonts
        self.font_or     = pygame.font.SysFont("dejavusans", int(self.H * 0.07), bold=True)
        self.font_option = pygame.font.SysFont("dejavusans", int(self.H * 0.065), bold=True)
        self.font_pct    = pygame.font.SysFont("dejavusans", int(self.H * 0.10), bold=True)
        self.font_votes  = pygame.font.SysFont("dejavusans", int(self.H * 0.028))
        self.font_small  = pygame.font.SysFont("dejavusans", int(self.H * 0.032))

        # Questions
        indices = list(range(len(QUESTIONS)))
        random.shuffle(indices)
        self.question_indices = indices
        self.questions = [QUESTIONS[index] for index in indices]
        self.q_index     = 0

        # State machine
        # "voting"  → show question, accept votes
        # "results" → show percentages
        self.state       = "voting"
        self.state_timer = time.time()

        # Particles / bubbles disabled
        self.particles   = []
        self.particle_timer = 0

        # Vote data
        self.counts = {"IRSensor 1": 0, "IRSensor 2": 0}
        self._read_json()

        # Animation
        self.anim_t      = 0.0   # 0→1 fade-in on question change
        self.last_total  = sum(self.counts.values())

        #skip button
        self.skip_rect = pygame.Rect(0, 0, 0, 0)
    
        #Arduino linking
        # Trash compactor state
        self.trash_level = 0
        self.trash_status = "IDLE"
        self._start_serial_thread()


    # ── helpers ─────────────────────────────
    def _read_json(self):
        try:
            with open(DATA_PATH, "r") as f:
                self.counts = json.load(f)
        except Exception:
            pass

    def _reset_json(self):
        fresh = {k: 0 for k in self.counts}
        try:
            if self.reset_counts_callback:
                self.reset_counts_callback(fresh)
            else:
                with open(DATA_PATH, "w") as f:
                    json.dump(fresh, f, indent=4)
        except Exception:
            pass
        self.counts = fresh
    
    def _load_scores(self):
        try:
            with open(SCORES_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_scores(self):
        scores = self._load_scores()
        original_index = str(self.question_indices[self.q_index % len(self.questions)])
        s1 = self.counts.get("IRSensor 1", 0)
        s2 = self.counts.get("IRSensor 2", 0)
        prev = scores.get(original_index, [0, 0])
        scores[original_index] = [prev[0] + s1, prev[1] + s2]
        with open(SCORES_PATH, "w") as f:
            json.dump(scores, f, indent=4)

    def _current_question(self):
        return self.questions[self.q_index % len(self.questions)]

    def _next_question(self):
        self._save_scores()
        self.q_index += 1
        self._reset_json()
        self.state       = "voting"
        self.state_timer = time.time()
        self.anim_t      = 0.0
        self.last_total  = 0

    def _percentages(self):
        if self.state == "results":
            scores = self._load_scores()
            original_index = str(self.question_indices[self.q_index % len(self.questions)])
            prev = scores.get(original_index, [0, 0])
            s1 = prev[0] + self.counts.get("IRSensor 1", 0)
            s2 = prev[1] + self.counts.get("IRSensor 2", 0)

        else:
            s1 = self.counts.get("IRSensor 1", 0)
            s2 = self.counts.get("IRSensor 2", 0)

        total = s1 + s2
        if total == 0:
            return 0.0, 0.0, 0
        
        return round(s1 / total * 100, 1), round(s2 / total * 100, 1), total

    #----trash compressing----------------
    def _start_serial_thread(self):
        def read_serial():
            try:
                ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
                while True:
                    line = ser.readline().decode("utf-8").strip()
                    if line.startswith("{"):
                        data = json.loads(line)
                        # self.trash_level = data.get("level", 0)
                        self.trash_status = data.get("status", "IDLE")
            except Exception as e:
                self.trash_status = "DISCONNECTED"
        threading.Thread(target=read_serial, daemon=True).start()

    def _draw_trash_overlay(self):
        # ── Top-left small info (always visible) ──
        pad = 12
        # txt1 = self.font_small.render(f"Trash: {self.trash_level}%", True, (255, 255, 255))
        txt2 = self.font_small.render(f"Status: {self.trash_status}", True, (255, 255, 255))
        # self.screen.blit(txt1, (pad, pad))
        # self.screen.blit(txt2, (pad, pad + txt1.get_height() + 4))
        self.screen.blit(txt2, (pad, pad))  

        # ── Center popup (only when not IDLE) ──
        if self.trash_status != "IDLE":
            box_w, box_h = int(self.W * 0.5), int(self.H * 0.3)
            box_x = (self.W - box_w) // 2
            box_y = (self.H - box_h) // 2

            # Transparent white rectangle
            s = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
            pygame.draw.rect(s, (255, 255, 255, 200), (0, 0, box_w, box_h), border_radius=20)
            self.screen.blit(s, (box_x, box_y))

            # Status text
            status_surf = self.font_pct.render(self.trash_status, True, (20, 20, 20))
            self.screen.blit(status_surf, (
                box_x + (box_w - status_surf.get_width()) // 2,
                box_y + int(box_h * 0.2)
            ))

            # Warning text
            warn_surf = self.font_small.render("Do not throw trash right now", True, (20, 20, 20))
            self.screen.blit(warn_surf, (
                box_x + (box_w - warn_surf.get_width()) // 2,
                box_y + int(box_h * 0.6)
            ))
    
    # ── drawing ─────────────────────────────
    def _draw_card(self, rect, grad_top, grad_bot, label, sublabel=None):
        """Draw one half-card with gradient + text."""
        draw_gradient_rect(self.screen, rect, grad_top, grad_bot)

        # Rounded corner mask (simple: draw dark bg rects at corners)
        r = 28
        card_surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(card_surf, (255, 255, 255, 255), (0, 0, rect[2], rect[3]), border_radius=r)
        # We'll use a clip approach — just draw text directly; corners are fine on fullscreen split

        text_rect = pygame.Rect(rect[0], rect[1], rect[2], rect[3])

        if sublabel:
            # Option text above centre, percentage below
            mid_y = rect[1] + rect[3] // 2 - int(self.H * 0.06)
            opt_rect  = pygame.Rect(rect[0], mid_y - int(self.H * 0.08), rect[2], int(self.H * 0.12))
            pct_rect  = pygame.Rect(rect[0], mid_y + int(self.H * 0.02), rect[2], int(self.H * 0.14))
            render_wrapped(self.screen, label,    self.font_option, (255,255,255), opt_rect)
            render_wrapped(self.screen, sublabel, self.font_pct,    (255,255,255), pct_rect)
        else:
            render_wrapped(self.screen, label, self.font_option, (255,255,255), text_rect)

    def _draw_or_badge(self):
        """Draw the 'would you rather' pill in the centre."""
        cx = self.W // 2 
        cy = self.H // 2 - 150

        lines = ["would", "you", "rather?"]
        line_h = self.font_or.get_linesize()
        total_h = line_h * len(lines)
        pad_x, pad_y = 28, 20

        max_w = max(self.font_or.size(ln)[0] for ln in lines)
        box_w = max_w + pad_x * 2
        box_h = total_h + pad_y * 2

        # Shadow
        shadow = pygame.Surface((box_w + 8, box_h + 8), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 80), (4, 4, box_w, box_h), border_radius=18)
        self.screen.blit(shadow, (cx - box_w // 2 - 2, cy - box_h // 2 - 2))

        # Badge background
        badge = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(badge, (20, 20, 30, 230), (0, 0, box_w, box_h), border_radius=18)
        self.screen.blit(badge, (cx - box_w // 2, cy - box_h // 2))

        # Text
        for i, ln in enumerate(lines):
            surf = self.font_or.render(ln, True, (255, 255, 255))
            x = cx - surf.get_width() // 2
            y = cy - total_h // 2 + i * line_h + pad_y // 2
            self.screen.blit(surf, (x, y))

    def _draw_vote_count(self, total):
        txt = self.font_votes.render(f"{total:,} votes", True, (255, 255, 255, 180))
        s = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        s.blit(txt, (0, 0))
        self.screen.blit(txt, (self.W // 2 - txt.get_width() // 2, self.H - int(self.H * 0.06)))

    def _draw_skip_button(self):
        btn_w, btn_h = 100, 40
        btn_x = self.W - btn_w - 20
        btn_y = self.H - btn_h - 20
        self.skip_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        # Transparent dark background
        s = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, 120), (0, 0, btn_w, btn_h), border_radius=10) # change to 180 for darker or 60 to more see through
        self.screen.blit(s, (btn_x, btn_y))

        # Skip text centered
        txt = self.font_small.render("skip", True, (255, 255, 255))
        self.screen.blit(txt, (btn_x + (btn_w - txt.get_width()) // 2,
                            btn_y + (btn_h - txt.get_height()) // 2))

    def _spawn_particles(self):
        half = self.W // 2
        for _ in range(2):
            self.particles.append(Particle(
                random.randint(0, half - 1),
                self.H + 5, half, self.H))
            self.particles.append(Particle(
                random.randint(half, self.W - 1),
                self.H + 5, half, self.H))
 
    def _update_particles(self):
        self.particles = [p for p in self.particles if p.is_alive()]
        for p in self.particles:
            p.update()

    # ── main loop ───────────────────────────
    def run(self):
        last_poll = time.time()

        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.anim_t = min(1.0, self.anim_t + dt * 1.5)

            # ── Events ──────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    if event.key == pygame.K_n:      # manual next (debug)
                        self._next_question()
                    if event.key == pygame.K_r:      # reset counts (debug)
                        self._reset_json()
                if event.type == pygame.MOUSEBUTTONDOWN: #skip button
                    if self.skip_rect.collidepoint(event.pos):
                        self._next_question()                

            # ── Poll JSON ───────────────────
            now = time.time()
            if now - last_poll >= POLL_INTERVAL:
                self._read_json()
                last_poll = now

            pct1, pct2, total = self._percentages()

            # ── State transitions ────────────
            if self.state == "voting":
                if total >= VOTE_THRESHOLD and now - self.state_timer >= 2.0:
                    self.state = "results"
                    self.state_timer = now

            elif self.state == "results":
                if now - self.state_timer >= RESULT_DURATION:
                    self._next_question()
                    continue

            # ── Particles ───────────────────
            # self.particle_timer += dt
            # if self.particle_timer >= 0.08:
            #     self._spawn_particles()
            #     self.particle_timer = 0
            # self._update_particles()

            # ── Draw ────────────────────────
            self.screen.fill((15, 15, 20))

            half = self.W // 2
            gap  = 6   # small gap between cards
            lw   = half - gap // 2
            rw   = self.W - half - gap // 2
            rx   = half + gap // 2

            left_q, right_q = self._current_question()

            alpha = int(255 * self._ease(self.anim_t))

            if self.state == "voting":
                self._draw_card((0,   0, lw, self.H), LEFT_GRAD[0],  LEFT_GRAD[1],  left_q)
                self._draw_card((rx,  0, rw, self.H), RIGHT_GRAD[0], RIGHT_GRAD[1], right_q)

            else:  # results
                # Winner keeps colour, loser goes grey
                if pct1 >= pct2:
                    l_top, l_bot = LEFT_GRAD
                    r_top, r_bot = GREY_TOP, GREY_BOT
                else:
                    l_top, l_bot = GREY_TOP, GREY_BOT
                    r_top, r_bot = RIGHT_GRAD

                self._draw_card((0,  0, lw, self.H), l_top, l_bot, left_q,  f"{pct1}%")
                self._draw_card((rx, 0, rw, self.H), r_top, r_bot, right_q, f"{pct2}%")
                self._draw_vote_count(total)

            # Particles on top
            # for p in self.particles:
            #     p.draw(self.screen)
            
            #skip button
            self._draw_skip_button()

            #arduino trash receiving
            self._draw_trash_overlay()

            # Centre badge last (always on top)
            self._draw_or_badge()

            pygame.display.flip()

    @staticmethod
    def _ease(t):
        """Smooth ease-in-out."""
        return t * t * (3 - 2 * t)


# ─────────────────────────────────────────────
#  Entry point (can run standalone for testing)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    WouldYouRatherDisplay().run()
