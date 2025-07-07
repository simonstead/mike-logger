import random

class Player:
    def __init__(self, name):
        self.name = name
        self.score = 0
        self.level = 1

    def update_score(self, points):
        self.score += points

    def level_up(self):
        self.level += 1

class Game:
    def __init__(self, num_players):
        self.players = [Player(f"Player {i+1}") for i in range(num_players)]
        self.current_level = 1

    def play_round(self):
        print(f"Welcome to Level {self.current_level}!")

        for player in self.players:
            points = random.randint(10, 50)
            player.update_score(points)
            print(f"{player.name} scored {points} points!")

        if all(player.score >= self.current_level * 100 for player in self.players):
            self.current_level += 1
            print("All players have reached the next level!")
            for player in self.players:
                player.level_up()
        else:
            print("Not all players have reached the next level yet.")

    def run_game(self):
        while self.current_level <= 5:
            self.play_round()
        print("Game over!")
        for player in self.players:
            print(f"{player.name} reached level {player.level} with a score of {player.score}.")

# Example usage
game = Game(4)
game.run_game()