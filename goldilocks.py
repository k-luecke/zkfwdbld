# Goldilocks Prime: 2^64 - 2^32 + 1
P = 0xFFFFFFFF00000001

def goldilocks_add(a, b):
    return (a + b) % P

def goldilocks_mul(a, b):
    return (a * b) % P

# Test a "Curvature Score" calculation in the field
score_val = 123456789
entropy_val = 987654321
field_element = goldilocks_add(score_val, -entropy_val % P)
print(f"Field Element representation: {field_element}")
