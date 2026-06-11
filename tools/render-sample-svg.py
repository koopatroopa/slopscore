#!/usr/bin/env python3
"""Render a sample slopscore report as a self-contained SVG for the README.

Hand-rolled (no dependency) so it renders crisply on GitHub in any theme and
regenerates deterministically. Mirrors the real terminal report: band-coloured
badge with a drop shadow, red verdict, cyan contributions, dimmed evidence.
"""

from pathlib import Path

BG = "#0d1117"        # GitHub dark canvas
FG = "#c9d1d9"        # default text
DIM = "#6e7681"       # evidence
CYAN = "#39c5cf"      # contributions
RED = "#f85149"       # HIGH band / FLAG
BADGE_BG = "#b62324"  # HIGH badge background
BADGE_FG = "#ffffff"
SHADOW = "#5c0f0f"    # darker red shadow
LH = 20               # line height
X = 16                # left pad
FONT = "ui-monospace, 'SF Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"

# (text, colour, bold) segments per line; "BADGE" = header, None = blank.
WORDMARK = " SLOPSCORE SLOP REPORT "

# A real commit scan: message + staged diff. Shows the three signal classes -
# attribution, a code stub with path:line, and a chatbot opener - and the
# certain-attribution floor (D-13) landing it in HIGH.
DEMO = [
    ("BADGE", " SLOPSCORE PUSH CHECK ", "[a1b2c3d] Add the request handler"),
    None,
    [("Slop score ", FG, 0), ("70.0/100", RED, 1), ("  band ", FG, 0),
     ("HIGH", RED, 1), ("  verdict ", FG, 0), ("FLAG", RED, 1),
     ("  (raw 8.0, threshold 30.0)", FG, 0)],
    None,
    [("Signals fired (3):", FG, 0)],
    [("  [+4.0] ", CYAN, 0), ("ai_self_reference", FG, 1),
     ("  x1  Explicit AI attribution or assistant self-reference", FG, 0)],
    [("         Evidence: Generated with Claude", DIM, 0)],
    [("  [+3.0] ", CYAN, 0), ("code_placeholder_stub", FG, 1),
     ("  x1  Placeholder/stub markers left in code", FG, 0)],
    [("         Evidence: handler.py:2: # ... rest of the code unchanged", DIM, 0)],
    [("  [+1.0] ", CYAN, 0), ("sycophantic_openers", FG, 1),
     ("  x1  Chatbot-style enthusiastic or deferential openers", FG, 0)],
    [("         Evidence: Certainly!", DIM, 0)],
    None,
    [("Verdict: ", FG, 0), ("FLAG", RED, 1),
     ("  (score 70.0 >= threshold 30.0)", FG, 0)],
]

# The real all-signals scan of this README - it wears the fingerprints it documents.
README_SCAN = [
    ("BADGE", " SLOPSCORE SLOP REPORT ", None),
    None,
    [("Slop score ", FG, 0), ("100.0/100", RED, 1), ("  band ", FG, 0),
     ("HIGH", RED, 1), ("  verdict ", FG, 0), ("FLAG", RED, 1),
     ("  (raw 14.25, threshold 30.0)", FG, 0)],
    None,
    [("Signals fired (9):", FG, 0)],
    [("  [+4.0] ", CYAN, 0), ("ai_self_reference", FG, 1), ("  x6 (capped 1)", FG, 0)],
    [("  [+2.0] ", CYAN, 0), ("ai_cliche_phrases", FG, 1), ("  x4 (capped 2)", FG, 0)],
    [("  [+2.0] ", CYAN, 0), ("sycophantic_openers", FG, 1), ("  x7 (capped 2)", FG, 0)],
    [("  [+1.5] ", CYAN, 0), ("promotional_adjectives", FG, 1), ("  x3", FG, 0)],
    [("  [+1.0] ", CYAN, 0), ("negative_parallelism", FG, 1), ("  x1", FG, 0)],
    [("  [+1.0] ", CYAN, 0), ("rhetorical_qa", FG, 1), ("  x1", FG, 0)],
    [("  [+1.0] ", CYAN, 0), ("vague_authority", FG, 1), ("  x1", FG, 0)],
    [("  [+1.0] ", CYAN, 0), ("emoji_density", FG, 1), ("  x1  Decorative emoji", FG, 0)],
    [("  [+0.75] ", CYAN, 0), ("em_dash_density", FG, 1), ("  x1", FG, 0)],
    None,
    [("Verdict: ", FG, 0), ("FLAG", RED, 1),
     ("  (score 100.0 >= threshold 30.0)", FG, 0)],
]

# The raw-text echo demo: `echo "Certainly! ... Generated with Claude Code." | slopscore --text -`
TEXT_DEMO = [
    ("BADGE", " SLOPSCORE SLOP REPORT ", None),
    None,
    [("Slop score ", FG, 0), ("75.0/100", RED, 1), ("  band ", FG, 0),
     ("HIGH", RED, 1), ("  verdict ", FG, 0), ("FLAG", RED, 1),
     ("  (raw 6.0, threshold 30.0)", FG, 0)],
    None,
    [("Signals fired (3):", FG, 0)],
    [("  [+4.0] ", CYAN, 0), ("ai_self_reference", FG, 1),
     ("  x1  Explicit AI attribution or assistant self-reference", FG, 0)],
    [("         Evidence: Generated with Claude", DIM, 0)],
    [("  [+1.0] ", CYAN, 0), ("ai_cliche_phrases", FG, 1),
     ("  x1  Filler and transition phrases characteristic of LLM prose", FG, 0)],
    [("         Evidence: delve into", DIM, 0)],
    [("  [+1.0] ", CYAN, 0), ("sycophantic_openers", FG, 1),
     ("  x1  Chatbot-style enthusiastic or deferential openers", FG, 0)],
    [("         Evidence: Certainly!", DIM, 0)],
    None,
    [("Verdict: ", FG, 0), ("FLAG", RED, 1),
     ("  (score 75.0 >= threshold 30.0)", FG, 0)],
]

CW = 7.7  # monospace char advance at 13px


def render(lines, dest_name):
  W = 760
  H = LH * len(lines) + 24
  out = [
      f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
      f'font-family="{FONT}" font-size="13px">',
      f'<rect width="{W}" height="{H}" rx="8" fill="{BG}"/>',
  ]
  y = 24
  for line in lines:
      if isinstance(line, tuple) and line[0] == "BADGE":
          _, wordmark, label = line
          bw = len(wordmark) * CW
          out.append(f'<rect x="{X+3}" y="{y+4}" width="{bw}" height="{LH}" fill="{SHADOW}"/>')
          out.append(f'<rect x="{X}" y="{y-14}" width="{bw}" height="{LH}" fill="{BADGE_BG}"/>')
          out.append(
              f'<text x="{X}" y="{y}" fill="{BADGE_FG}" font-weight="bold" '
              f'xml:space="preserve">{wordmark}</text>'
          )
          if label:
              lx = X + bw + 12
              esc = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
              out.append(
                  f'<text x="{lx:.1f}" y="{y}" fill="{FG}" font-weight="bold" '
                  f'xml:space="preserve">{esc}</text>'
              )
          y += LH + 6
          continue
      if line is None:
          y += LH
          continue
      x = X
      for text, colour, bold in line:
          esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
          weight = ' font-weight="bold"' if bold else ""
          out.append(
              f'<text x="{x:.1f}" y="{y}" fill="{colour}"{weight} '
              f'xml:space="preserve">{esc}</text>'
          )
          x += len(text) * CW
      y += LH
  out.append("</svg>")
  dest = Path(__file__).resolve().parent.parent / "assets" / dest_name
  dest.parent.mkdir(exist_ok=True)
  dest.write_text("\n".join(out), encoding="utf-8")
  print(f"wrote {dest}")


render(DEMO, "sample-report.svg")
render(TEXT_DEMO, "text-demo.svg")
render(README_SCAN, "readme-scan.svg")
