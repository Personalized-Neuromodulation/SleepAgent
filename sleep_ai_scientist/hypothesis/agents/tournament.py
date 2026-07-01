from __future__ import annotations

import math
from dataclasses import dataclass


GLICKO2_SCALE = 173.7178
TAU = 0.5
DEFAULT_RATING = 1200
DEFAULT_RD = 350
DEFAULT_VOLATILITY = 0.06
REVIEWED_RD = 200


@dataclass(frozen=True)
class Glicko2State:
    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    volatility: float = DEFAULT_VOLATILITY
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0


def to_mu(rating: float) -> float:
    return (rating - 1500.0) / GLICKO2_SCALE


def to_phi(rd: float) -> float:
    return rd / GLICKO2_SCALE


def from_mu(mu: float) -> float:
    return mu * GLICKO2_SCALE + 1500.0


def from_phi(phi: float) -> float:
    return phi * GLICKO2_SCALE


def g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + (3.0 * phi * phi) / (math.pi * math.pi))


def expected_score(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-g(phi_j) * (mu - mu_j)))


def compute_new_volatility(phi: float, sigma: float, delta: float, variance: float) -> float:
    a = math.log(sigma * sigma)
    eps = 1e-6

    def f(x: float) -> float:
        ex = math.exp(x)
        denom_base = phi * phi + variance + ex
        numerator = ex * (delta * delta - denom_base)
        denominator = 2.0 * denom_base * denom_base
        return numerator / denominator - (x - a) / (TAU * TAU)

    A = a
    if delta * delta > phi * phi + variance:
        B = math.log(delta * delta - phi * phi - variance)
    else:
        k = 1
        while f(a - k * TAU) < 0 and k < 1000:
            k += 1
        B = a - k * TAU

    f_a = f(A)
    f_b = f(B)
    for _ in range(1000):
        if abs(B - A) <= eps:
            break
        C = A + ((A - B) * f_a) / (f_b - f_a)
        f_c = f(C)
        if f_c * f_b <= 0:
            A = B
            f_a = f_b
        else:
            f_a /= 2.0
        B = C
        f_b = f_c

    return math.exp(A / 2.0)


def _update_player(player: Glicko2State, opponent: Glicko2State, score: float) -> Glicko2State:
    mu = to_mu(player.rating)
    phi = to_phi(player.rd)
    mu_j = to_mu(opponent.rating)
    phi_j = to_phi(opponent.rd)

    g_phi_j = g(phi_j)
    e_val = max(1e-10, min(1.0 - 1e-10, expected_score(mu, mu_j, phi_j)))
    variance = 1.0 / (g_phi_j * g_phi_j * e_val * (1.0 - e_val))
    delta = variance * g_phi_j * (score - e_val)
    new_sigma = compute_new_volatility(phi, player.volatility, delta, variance)
    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / variance)
    new_mu = mu + new_phi * new_phi * g_phi_j * (score - e_val)

    won = score == 1.0
    drew = score == 0.5
    return Glicko2State(
        rating=round(from_mu(new_mu)),
        rd=min(350, round(from_phi(new_phi))),
        volatility=round(new_sigma, 6),
        matches_played=player.matches_played + 1,
        wins=player.wins + (1 if won else 0),
        losses=player.losses + (1 if not won and not drew else 0),
        draws=player.draws + (1 if drew else 0),
    )


def compute_glicko2_update(
    player_a: Glicko2State,
    player_b: Glicko2State,
    result: str,
) -> tuple[Glicko2State, Glicko2State]:
    score_a = 1.0 if result == "A_wins" else 0.0 if result == "B_wins" else 0.5
    score_b = 1.0 - score_a
    return _update_player(player_a, player_b, score_a), _update_player(player_b, player_a, score_b)


def seeded_glicko2_from_review_scores(
    novelty: float | None = None,
    correctness: float | None = None,
    testability: float | None = None,
) -> tuple[float, float, float]:
    scores = [score for score in [novelty, correctness, testability] if score is not None]
    if not scores:
        return DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY
    rating = round(1000 + (sum(scores) / len(scores) / 10.0) * 400)
    return rating, REVIEWED_RD, DEFAULT_VOLATILITY
