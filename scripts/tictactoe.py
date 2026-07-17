"""Tic-tac-toe on the profile README: the internet vs my bot.

Visitors click an empty square on the README board, which opens a
pre-filled GitHub issue (title "ttt|<1-9>"). A GitHub Action runs
this script, plays the bot's answer, rewrites the board between the
TTT markers in README.md, and closes the issue.

Usage:
  python scripts/tictactoe.py render                 rebuild README section only
  python scripts/tictactoe.py move "ttt|5" "<user>"  process one move
"""

import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "game", "state.json")
README_PATH = os.path.join(ROOT, "README.md")
MESSAGE_PATH = os.path.join(ROOT, "game", "last_message.txt")

REPO_URL = "https://github.com/madhu12-c/madhu12-c"
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6)]


def load_state():
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def winner(board):
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def bot_move(board):
    empties = [i for i, v in enumerate(board) if not v]
    for mark in ("O", "X"):          # take a win first, then block
        for i in empties:
            trial = board[:]
            trial[i] = mark
            if winner(trial) == mark:
                return i
    if 4 in empties:
        return 4
    corners = [i for i in (0, 2, 6, 8) if i in empties]
    if corners:
        return random.choice(corners)
    return random.choice(empties)


def render_board(state):
    board = state["board"]
    rows = []
    rows.append('<table align="center">')
    for r in range(3):
        rows.append("  <tr>")
        for c in range(3):
            i = r * 3 + c
            if board[i] == "X":
                cell = '<img src="assets/ttt/x.svg" width="70" alt="X"/>'
            elif board[i] == "O":
                cell = '<img src="assets/ttt/o.svg" width="70" alt="O"/>'
            else:
                url = ("{}/issues/new?title=ttt%7C{}&body=press+submit+and+my+bot+will"
                       "+answer+within+a+minute.+then+check+the+board+again.").format(REPO_URL, i + 1)
                cell = '<a href="{}"><img src="assets/ttt/empty.svg" width="70" alt="play square {}"/></a>'.format(url, i + 1)
            rows.append("    <td>{}</td>".format(cell))
        rows.append("  </tr>")
    rows.append("</table>")

    score = "**the internet** {} | **my bot** {} | draws {}".format(
        state["internet_wins"], state["bot_wins"], state["draws"])
    parts = ['<div align="center">', "", score, ""]
    if state.get("last_result"):
        parts += [state["last_result"], ""]
    parts += ["</div>", ""] + rows + [""]
    if state.get("recent"):
        players = ", ".join("[@{0}](https://github.com/{0})".format(p) for p in state["recent"][:5])
        parts += ['<div align="center"><sub>recent players: {}</sub></div>'.format(players), ""]
    return "\n".join(parts)


def render_readme(state):
    with open(README_PATH, encoding="utf-8") as f:
        readme = f.read()
    section = "<!-- TTT:START -->\n" + render_board(state) + "<!-- TTT:END -->"
    readme = re.sub(r"<!-- TTT:START -->.*?<!-- TTT:END -->", section, readme, flags=re.S)
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(readme)


def say(message):
    with open(MESSAGE_PATH, "w", encoding="utf-8") as f:
        f.write(message)
    print(message)


def cmd_move(title, author):
    match = re.fullmatch(r"ttt\|([1-9])", title.strip())
    if not match:
        say("that title does not look like a move. click a square on the board instead of editing the title.")
        return
    cell = int(match.group(1)) - 1
    state = load_state()
    board = state["board"]

    if board[cell]:
        say("square {} is already taken. pick an empty one: {}".format(
            cell + 1, REPO_URL))
        return

    board[cell] = "X"
    state["recent"] = [author] + [p for p in state.get("recent", []) if p != author]
    state["recent"] = state["recent"][:5]

    if winner(board) == "X":
        state["internet_wins"] += 1
        state["last_result"] = "last game: the internet beat my bot, finished by [@{0}](https://github.com/{0})".format(author)
        state["board"] = [""] * 9
        say("@{}: that was the winning move. the internet takes the round, fresh board is up.".format(author))
    elif all(board):
        state["draws"] += 1
        state["last_result"] = "last game: a draw, final move by [@{0}](https://github.com/{0})".format(author)
        state["board"] = [""] * 9
        say("@{}: board full, that one is a draw. fresh board is up.".format(author))
    else:
        board[bot_move(board)] = "O"
        if winner(board) == "O":
            state["bot_wins"] += 1
            state["last_result"] = "last game: my bot won. it is beatable, I promise."
            state["board"] = [""] * 9
            say("@{}: my bot took that round. fresh board is up, try again: {}".format(author, REPO_URL))
        elif all(board):
            state["draws"] += 1
            state["last_result"] = "last game: a draw, final move by [@{0}](https://github.com/{0})".format(author)
            state["board"] = [""] * 9
            say("@{}: board full, that one is a draw. fresh board is up.".format(author))
        else:
            say("@{}: your X is placed and my bot has answered. board: {}".format(author, REPO_URL))

    save_state(state)
    render_readme(state)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "move":
        cmd_move(sys.argv[2], sys.argv[3])
    else:
        render_readme(load_state())
        print("board rendered")


if __name__ == "__main__":
    main()
