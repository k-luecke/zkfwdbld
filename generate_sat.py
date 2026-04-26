import random

def generate_simple_sat(num_variables, num_clauses, filename="Heuristics/test_vector_1.cnf"):
    """Generates a random 3-SAT problem in DIMACS format."""
    with open(filename, "w") as f:
        f.write(f"c Simple 3-SAT Test Vector for Paxiom\n")
        f.write(f"p cnf {num_variables} {num_clauses}\n")
        for _ in range(num_clauses):
            # Pick 3 unique random variables
            vars = random.sample(range(1, num_variables + 1), 3)
            # Randomly negate them
            clause = [v if random.random() > 0.5 else -v for v in vars]
            f.write(f"{clause[0]} {clause[1]} {clause[2]} 0\n")
    print(f"Successfully staged {filename} with {num_clauses} clauses.")

# Stage a medium-sized problem
generate_simple_sat(num_variables=100, num_clauses=400)
