# AI Chess Arena

Pick any two AI language models and watch them play chess against each other.
Each model explains its thinking as it plays, and after the game a chess engine grades every move: who played more accurately, where the blunders were, and what the best move would have been.

## How a game works

- On each turn, the model sees the current position and the moves played so far, and answers with its move and a short explanation of why it chose it.
- Every move is checked against the rules of chess. If a model makes an illegal move, it's told what was wrong and gets a few more tries. A model that keeps failing forfeits the game.
- Like a chess clock, each move has a time limit. A model that keeps running out of time loses on time.
- Delays caused by the AI provider itself, such as a busy server, never count against a model.
- Every answer, its cost and its response time is recorded.

A game ends on checkmate, stalemate, a draw by the rules of chess, a forfeit, a loss on time, or when the move limit is reached.

## Move analysis

After the game, the [Stockfish](https://stockfishchess.org) chess engine reviews every move, using the same scoring as [Lichess](https://lichess.org/page/accuracy):

- **Move labels:** each move is marked as best, good, an inaccuracy, a mistake or a blunder, depending on how much of the player's winning chances it gave away.
- **Accuracy:** a score from 0 to 100 for each player. Blunders weigh more than good moves.
- **Best moves:** for every mistake, the move the engine would have played instead.

If a game reaches the move limit, the side the engine sees as clearly winning is declared the winner. Otherwise the game is a draw.

Every game can be exported in the standard chess format (PGN), with each model's explanations and the engine's verdicts as comments, so it can be replayed in any chess app.
