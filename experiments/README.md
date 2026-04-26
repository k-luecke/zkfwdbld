# Experiments

Local experiments for turning audit findings into measured engineering work.

## Prover Scaling

Run:

```sh
cargo run --release --example prover_scaling
```

The experiment generates deterministic satisfiable 3-SAT instances and measures:

- witness generation time,
- R1CS construction time,
- R1CS verification time.

The first run is captured in `prover_scaling_2026-04-26.csv`.
