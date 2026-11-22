# AI Chess Arena

Pick any two AI language models and watch them play chess against each other.
Each model explains its thinking as it plays. After the game, a chess engine grades every move, and an AI judge agent investigates the game and writes a report: what decided it, and whether each model's explanations matched what it actually played.

## How a game works

- On each turn, the model sees the current position and the moves played so far, and answers with its move and a short explanation of why it chose it.
- Every move is checked against the rules of chess. If a model makes an illegal move, it's told what was wrong and gets a few more tries. A model that keeps failing forfeits the game.
- Like a chess clock, each move has a time limit. A model that keeps running out of time loses on time.
- Delays caused by the AI provider itself, such as a busy server, never count against a model.
- Every answer, its cost and its response time is recorded.
- Games are played live: you can watch each move and its explanation the moment it's made, and every game is saved so it can be replayed later.

Games are played to the end: checkmate, stalemate, a draw by the rules of chess, a forfeit or a loss on time. A very high move limit exists only as a safety net.

## Move analysis

After the game, the [Stockfish](https://stockfishchess.org) chess engine reviews every move, using the same scoring as [Lichess](https://lichess.org/page/accuracy):

- **Move labels:** each move is marked as best, good, an inaccuracy, a mistake or a blunder, depending on how much of the player's winning chances it gave away.
- **Accuracy:** a score from 0 to 100 for each player. Blunders weigh more than good moves.
- **Best moves:** for every mistake, the move the engine would have played instead.

If a game ever reaches the safety move limit, the side the engine sees as clearly winning is declared the winner. Otherwise the game is a draw.

## The judge agent

When the engine is done, a judge agent (a reasoning AI model) reviews the game the way a chess commentator would. It isn't handed a summary: it investigates on its own, choosing which tools to use, such as looking up the turning points, reading what a model said about a move, or looking at the board at any moment.

Its main question is whether each model's explanations were true. Models often describe threats or plans that aren't on the board, and the judge points those out. It then writes a short report with a headline, the story of the game, its key moments and a grade from A to F for each player.

You can watch the judge work: every thought and every step it takes appears on the page as it happens, and stays with the game for later replays.

## Leaderboard

Every finished game counts toward a leaderboard of the models. Each model has a rating that starts at 1500 and goes up or down after every game, the way chess clubs rate players. Next to the rating are its wins, draws and losses, its average accuracy, the judge's average grade, and how often its explanations matched what it actually played. Losing by illegal moves or on time counts as a loss; a game stopped by the AI provider doesn't count at all.
