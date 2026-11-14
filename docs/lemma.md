# Why min(p, 1 − p) stalls and p(1 − p) does not

This note states and proves the result behind the query strategy of BRANCH (proposal v2, section 4.3). The paper states it in its Methods section.

## Setting

Two alternatives A and B. The open modelling choices are random variables X = (X_1, …, X_J) with prior distributions. The verdict indicator is

D = 1{I_A(X) < I_B(X)},  p = P(D = 1) = E[D].

Asking the human about choice j reveals X_j. A myopic strategy scores each open choice by the expected reduction of a loss g of the verdict probability (preposterior analysis; Howard 1966), the "expected error reduction" of active learning (Settles 2009):

R_g(j) = g(p) − E_{X_j}[ g(p_j(X_j)) ],  where p_j(x) = P(D = 1 | X_j = x).

By the law of total probability, E_{X_j}[p_j(X_j)] = p.

## Proposition 1 (the smooth loss is the Sobol index of the verdict)

For g(p) = p(1 − p),

R_g(j) = Var_{X_j}( E[D | X_j] ),  and  R_g(j) / g(p) = S_j(D),

where S_j(D) = Var(E[D | X_j]) / Var(D) is the first order Sobol sensitivity index of the verdict indicator D (Saltelli et al. 2008).

**Proof.** g(p) = p − p². Then
R_g(j) = p − p² − E[p_j − p_j²] = E[p_j²] − p²,
because E[p_j] = p. Since E[p_j] = p, E[p_j²] − p² = Var(p_j) = Var(E[D | X_j]). Finally D is a Bernoulli variable, so Var(D) = p(1 − p) = g(p), and dividing gives S_j(D). ∎

**Consequence.** Ranking choices by R_g is ranking them by the share of the verdict's variance each one explains. The usual LCA sensitivity analysis ranks by the share of the variance of the result, S_j(I_A − I_B), which can be large for a choice that never changes which alternative wins. This is the difference between the `sobol` baseline and `decision_flip`.

## Proposition 2 (the literal loss stalls)

For m(p) = min(p, 1 − p): if, for choice j, every answer leaves the verdict on the same side, that is p_j(x) ≤ 1/2 for all x when p ≤ 1/2 (or ≥ 1/2 for all x when p ≥ 1/2), then R_m(j) = 0.

**Proof.** Take p ≤ 1/2 and p_j(x) ≤ 1/2 for all x. Then m(p_j(x)) = p_j(x), so E[m(p_j)] = E[p_j] = p = m(p), and R_m(j) = 0. The case p ≥ 1/2 is symmetric with m(q) = 1 − q. ∎

**Consequence.** When no single answer can carry p across 1/2, which is the usual situation once the verdict leans one way but is not yet certified, every open choice scores exactly zero. The myopic agent has no ranking: it picks arbitrarily and behaves like `random` until a lucky answer moves p. This is the plateau seen in the curve of 26 October. By contrast g(p) = p(1 − p) is strictly concave, so R_g(j) = Var(p_j) > 0 as soon as the answer to j changes the verdict probability at all (Jensen's inequality), and the ranking never collapses.

## Proposition 3 (the two losses certify the same thing)

For every p in [0, 1],

m(p) ≤ 2 p(1 − p) ≤ 2 m(p).

**Proof.** Take p ≤ 1/2, so m(p) = p. Then 2p(1 − p) ≥ p because 1 − p ≥ 1/2, and 2p(1 − p) ≤ 2p because 1 − p ≤ 1. The case p ≥ 1/2 follows by symmetry. ∎

**Consequence.** Using p(1 − p) to choose questions does not change what is certified: BRANCH still stops when m(p) = P(verdict wrong) < τ, and driving p(1 − p) down drives m(p) down at the same rate up to a factor of 2.

## Note on the implementation

`branch/query.py` estimates p and every p_j(x_k) from the same Monte Carlo draws (common random numbers); the K answers of a continuous choice are represented by K quantile points of equal weight. Two estimators of R_g(j) follow:

- `decision_flip` (the strategy of the paper) takes the loss before the answer at the sample estimate of p. Its score is R(j) = [g(p) − g(p̄_j)] + Var_k(p_j(x_k)), with p̄_j = Σ_k w_k p_j(x_k). The bracket is a discretisation gap: it carries no information about j, but it differs between choices and can reorder them when the verdict probability sits in the tails that K quantile points do not represent.
- `decision_flip_tp` takes the loss before the answer at p̄_j, as the law of total probability requires. Its score is exactly p̄_j(1 − p̄_j) S_j(D), and `decision_flip_min_tp` scores exactly zero in the case of Proposition 2.

In a first check on 40 synthetic runs (40 choices, 5 000 samples) the total probability version asked more questions (2.35 against 1.38) and made no wrong certification (against 2). The benchmark of the paper reports both as an ablation, and the paper keeps `decision_flip`. `tests/test_lemma.py` checks the three propositions and both decompositions numerically.

## References

Howard, Ronald A. 1966. "Information Value Theory." *IEEE Transactions on Systems Science and Cybernetics* 2 (1): 22–26.

Saltelli, Andrea, Marco Ratto, Terry Andres, Francesca Campolongo, Jessica Cariboni, Debora Gatelli, Michaela Saisana, and Stefano Tarantola. 2008. *Global Sensitivity Analysis: The Primer*. Chichester: Wiley.

Settles, Burr. 2009. *Active Learning Literature Survey*. Computer Sciences Technical Report 1648. Madison: University of Wisconsin–Madison.
