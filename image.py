Python 3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)] on win32
Enter "help" below or click "Help" above for more information.
import random
import time
import threading
from collections import Counter
from PIL import Image, ImageDraw
GRID = 8
PIXEL = 32
word_counts = Counter()
cells = [None] * 64
# -----------------------------
# SCRABBLE
# -----------------------------
scores = {
    **dict.fromkeys(list("aeioulnstr"), 1),
    **dict.fromkeys(list("dg"), 2),
    **dict.fromkeys(list("bcmp"), 3),
    **dict.fromkeys(list("fhvwy"), 4),
    "k": 5,
    **dict.fromkeys(list("jx"), 😎,
    **dict.fromkeys(list("qz"), 10)
}
def word_score(w):
    return sum(scores.get(c, 0) for c in w)
def energy(w):
    return word_counts[w] * word_score(w)
# -----------------------------
# INPUT
# -----------------------------
def add_text(text):
    word_counts.update(text.lower().split())
# -----------------------------
# SIMILARITY TO SENTENCE
# -----------------------------
def similarity(word, sentence):
    return sum(1 for c in word if c in sentence)
# -----------------------------
# UPDATE FIELD
# -----------------------------
def update_field(sentence):
    words = list(word_counts.keys())
    for i in range(64):
        if not words:
            continue
        # pick candidates weighted by energy + similarity
        weighted = sorted(
            words,
...             key=lambda w: energy(w) + similarity(w, sentence),
...             reverse=True
...         )
...         candidate = random.choice(weighted[:10])
...         if cells[i] is None:
...             cells[i] = candidate
...         else:
...             if energy(candidate) > energy(cells[i]):
...                 cells[i] = candidate
... # -----------------------------
... # COLOR MAPPING
... # -----------------------------
... def word_color(word, sentence):
...     e = energy(word)
...     s = similarity(word, sentence)
...     r = min(255, e * 5)
...     g = min(255, s * 40)
...     b = 150
...     return (r, g, b)
... # -----------------------------
... # DRAW
... # -----------------------------
... def draw_image(sentence):
...     size = GRID * PIXEL
...     img = Image.new("RGB", (size, size), "black")
...     draw = ImageDraw.Draw(img)
...     for i, w in enumerate(cells):
...         if not w:
...             continue
...         x = (i % GRID) * PIXEL
...         y = (i // GRID) * PIXEL
...         draw.rectangle(
...             [x, y, x + PIXEL, y + PIXEL],
...             fill=word_color(w, sentence)
...         )
...     img.save("output.png")
... # -----------------------------
... # LOOP
... # -----------------------------
... def loop(sentence):
...     while True:
...         update_field(sentence)
...         draw_image(sentence)
        print("Frame updated")
        time.sleep(10)
# -----------------------------
# MAIN
# -----------------------------
def main():
    print("Feed chat (type 'done'):")
    while True:
        line = input("> ")
        if line == "done":
            break
        add_text(line)
    sentence = input("Driver sentence: ").lower()
    t = threading.Thread(target=loop, args=(sentence,))
    t.daemon = True
    t.start()
    while True:
        time.sleep(1)
if __name__ == "__main__":
