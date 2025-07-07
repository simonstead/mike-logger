"""
This Python script calculates the Fibonacci sequence up to a given number of terms.

The Fibonacci sequence is a series of numbers where each number is the sum of the two preceding ones, usually starting with 0 and 1. The sequence goes as follows: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, and so on.

This script allows the user to specify the number of Fibonacci terms to generate and then prints out the sequence.
"""

def fibonacci(n):
    """
    Calculates the Fibonacci sequence up to the nth term.

    Args:
        n (int): The number of Fibonacci terms to generate.

    Returns:
        list: A list containing the Fibonacci sequence up to the nth term.
    """
    sequence = [0, 1]
    if n <= 2:
        return sequence[:n]
    else:
        for i in range(2, n):
            next_term = sequence[-1] + sequence[-2]
            sequence.append(next_term)
        return sequence

# Get the number of Fibonacci terms from the user
num_terms = int(input("Enter the number of Fibonacci terms to generate: "))

# Calculate and print the Fibonacci sequence
fib_sequence = fibonacci(num_terms)
print(f"The Fibonacci sequence up to {num_terms} terms is: {fib_sequence}")