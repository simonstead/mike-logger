import random

class Player:
    def __init__(self, name):
        self.name = name
        self.score = 0
        self.level = 1

    def increase_score(self, points):
        self.score += points

    def level_up(self):
        self.level += 1

class Game:
    def __init__(self):
        self.players = []
        self.current_level = 1

    def add_player(self, player):
        self.players.append(player)

    def start_game(self):
        print("Welcome to the game!")
        while self.current_level <= 5:
            self.play_level()
            self.current_level += 1
        self.display_results()

    def play_level(self):
        print(f"Level {self.current_level}")
        for player in self.players:
            points = random.randint(10, 50)
            player.increase_score(points)
            print(f"{player.name} scored {points} points!")
            if player.score >= self.current_level * 100:
                player.level_up()
                print(f"{player.name} leveled up to level {player.level}!")

    def display_results(self):
        print("Game over!")
        for player in self.players:
            print(f"{player.name} final score: {player.score}, final level: {player.level}")

# Example usage
player1 = Player("Alice")
player2 = Player("Bob")
game = Game()
game.add_player(player1)
game.add_player(player2)
game.start_game()