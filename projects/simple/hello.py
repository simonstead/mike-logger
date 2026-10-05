import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

logging.info('Hello from verbose logging!')

"""
Fibonacci Numbers

Fibonacci numbers are a sequence of numbers where each number is the sum of the two preceding ones, usually starting with 0 and 1. 
The sequence goes like this: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, and so on.

The Fibonacci sequence has many interesting properties and applications, including:

- It appears in nature, such as in the spiral patterns of seashells, pinecones, and flower petals.
- It is used in various mathematical and computer science concepts, like the golden ratio and algorithm analysis.
- It has connections to the Lucas numbers, Pascal's triangle, and other mathematical sequences.

The Fibonacci sequence is defined by the recurrence relation:

F(n) = F(n-1) + F(n-2)

where F(0) = 0 and F(1) = 1.

This simple script demonstrates the basic concept of Fibonacci numbers and how to print a message using verbose logging in Python.
"""