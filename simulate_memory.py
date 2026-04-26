import sys

def simulate_matrix_memory(num_constraints):
    # Each constraint in a sparse matrix is usually (row, col, value)
    # usize (8 bytes) + usize (8 bytes) + field_element (8 bytes) = 24 bytes per entry
    entries_per_row = 3
    num_matrices = 3 # A, B, C
    
    total_entries = num_constraints * entries_per_row * num_matrices
    total_memory_gb = (total_entries * 24) / 1e9
    
    print(f"Simulated R1CS Memory Load: {total_memory_gb:.2f} GB")
    if total_memory_gb > 4: # Assuming ~4GB available based on your 71% idle
        print("WARNING: Site memory is insufficient for 16M constraints. Implementation of 'Streaming' required.")

simulate_matrix_memory(16_000_000)
