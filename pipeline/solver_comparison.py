"""
Offline solver comparison for the cleaning-schedule window sub-problem: is SLSQP +
bang-bang rounding (the production solver in cleaning_scheduler_network.py) leaving
real savings on the table versus solving the SAME window as a genuine mixed-integer
problem?

WHY THIS EXISTS: `solve_window()` relaxes the true binary decision y[hx,t] in {0,1}
(clean this HX this period, or don't) to continuous [0,1], solves with SLSQP, then
rounds. That is fast and has a track record of bug-fixes/validation (see
cleaning_scheduler_network.py's docstring and comparison_vs_v1 logic), but it is a
relaxation, not an exact solver for the integer problem — rounding a continuous
optimum is not guaranteed to be the integer optimum. This script solves the exact
same `window_objective` (same THB, same constraints) with two independent methods
that do NOT rely on continuous relaxation + rounding:

  1. "MINLP-style" global solver: scipy.optimize.differential_evolution with
     `integrality=True` on every decision variable. This is scipy's built-in
     mixed-integer nonlinear global optimizer (available without any extra
     dependency — scipy is already required everywhere in this project). It is
     NOT the same as installing Pyomo + Bonmin/Couenne (a full deterministic MINLP
     solver with an optimality-gap certificate), which this environment doesn't
     have and which would be a heavy, likely install-breaking addition for a
     project that deliberately keeps dependencies light (see requirements-full.txt's
     own comment about avoiding heavy installs unless the payoff is worth it). This
     is the pragmatic, honest middle ground: a genuine mixed-integer global search,
     just not one with a certified optimality gap.
  2. Genetic Algorithm: a small, dependency-free GA (binary chromosome = the exact
     y[hx,t] flattened bit vector, tournament selection, uniform crossover, bit-flip
     mutation, elitism, constraint handled by penalty). Requested explicitly as a
     metaheuristic cross-check independent of scipy's DE implementation.

Both are scored on the IDENTICAL `window_objective` (same THB units, same crew-cap
constraint) that SLSQP already optimizes, so objective value is directly comparable
across all three. Run standalone: python pipeline/solver_comparison.py
"""
import sys, time
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution, NonlinearConstraint

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / 'pipeline'))
import cleaning_scheduler_network as NS


def solve_window_de(dev0, r, cost, k_per_day, n_t, crew_cap, seed=0, maxiter=150, popsize=20):
    """scipy differential_evolution with integrality=True -- a genuine mixed-integer
    global search on the exact same objective SLSQP solves (see module docstring)."""
    n_hx = len(dev0)
    n_vars = n_hx * n_t
    if n_hx == 0 or n_t == 0:
        return np.zeros((n_hx, max(n_t, 0))), 0.0, 0.0

    bounds = [(0, 1)] * n_vars
    constraints = ()
    if crew_cap and n_hx > 1:
        # same constraint as SLSQP's solve_window: sum_hx y[:,t] <= crew_cap for each period t,
        # expressed as a linear-in-y NonlinearConstraint (DE's constraint API wants callables).
        def crew_cap_fun(x, n_hx=n_hx, n_t=n_t):
            y = x.reshape(n_hx, n_t)
            return y.sum(axis=0)   # one value per period t
        constraints = (NonlinearConstraint(crew_cap_fun, -np.inf, crew_cap),)

    t0 = time.time()
    res = differential_evolution(
        NS.window_objective, bounds, args=(dev0, r, cost, k_per_day, n_hx, n_t),
        integrality=[True] * n_vars, constraints=constraints,
        seed=seed, maxiter=maxiter, popsize=popsize, polish=False, tol=1e-8)
    dt = time.time() - t0
    y = np.round(res.x).reshape(n_hx, n_t)
    return y, res.fun, dt


def solve_window_ga(dev0, r, cost, k_per_day, n_t, crew_cap, seed=0,
                     pop_size=80, n_generations=120, crossover_p=0.7,
                     tournament_k=3, elite_n=2, penalty_per_violation=50.0):
    """Small dependency-free genetic algorithm on the exact same objective, with the
    crew-cap constraint handled as a fitness penalty (standard GA practice, since GA
    has no native constraint-handling the way SLSQP/DE do)."""
    n_hx = len(dev0)
    n_genes = n_hx * n_t
    if n_hx == 0 or n_t == 0:
        return np.zeros((n_hx, max(n_t, 0))), 0.0, 0.0

    rng = np.random.RandomState(seed)

    def fitness(pop):
        """pop: (pop_size, n_genes) binary. Returns penalized objective (lower=better)."""
        obj = np.array([NS.window_objective(ind, dev0, r, cost, k_per_day, n_hx, n_t)
                        for ind in pop])
        if crew_cap and n_hx > 1:
            y = pop.reshape(len(pop), n_hx, n_t)
            over = np.clip(y.sum(axis=1) - crew_cap, 0, None)   # (pop_size, n_t)
            obj = obj + penalty_per_violation * over.sum(axis=1)
        return obj

    t0 = time.time()
    pop = rng.randint(0, 2, size=(pop_size, n_genes)).astype(float)
    best_x, best_f = None, np.inf
    for gen in range(n_generations):
        scores = fitness(pop)
        gen_best_idx = np.argmin(scores)
        if scores[gen_best_idx] < best_f:
            best_f, best_x = scores[gen_best_idx], pop[gen_best_idx].copy()

        # elitism
        elite_idx = np.argsort(scores)[:elite_n]
        new_pop = [pop[i].copy() for i in elite_idx]

        # tournament selection + uniform crossover + bit-flip mutation
        while len(new_pop) < pop_size:
            def tournament():
                cand = rng.choice(pop_size, size=tournament_k, replace=False)
                return pop[cand[np.argmin(scores[cand])]]
            p1, p2 = tournament(), tournament()
            if rng.rand() < crossover_p:
                mask = rng.rand(n_genes) < 0.5
                child = np.where(mask, p1, p2)
            else:
                child = p1.copy()
            mut_mask = rng.rand(n_genes) < (1.0 / n_genes)
            child[mut_mask] = 1 - child[mut_mask]
            new_pop.append(child)
        pop = np.array(new_pop[:pop_size])
    dt = time.time() - t0

    # re-score the true (unpenalized) objective for the reported value, since the
    # penalty is a search aid, not the real cost SLSQP/DE are compared on
    true_obj = NS.window_objective(best_x, dev0, r, cost, k_per_day, n_hx, n_t)
    return best_x.reshape(n_hx, n_t), true_obj, dt


def compare_one_window(dev0, r, cost, k_per_day, n_t, crew_cap, seed=0):
    """Solve ONE representative window (the unit SLSQP actually optimizes at each
    step of the moving-window schedule) three ways and report objective (THB, since
    OBJ_SCALE is applied consistently by all three via window_objective) + solve time."""
    t0 = time.time()
    y_slsqp = NS.solve_window(dev0, r, cost, k_per_day, n_t)
    dt_slsqp = time.time() - t0
    y_slsqp_rounded = np.round(np.clip(y_slsqp, 0, 1))
    obj_slsqp = NS.window_objective(y_slsqp_rounded.ravel(), dev0, r, cost, k_per_day, len(dev0), n_t)

    y_de, obj_de, dt_de = solve_window_de(dev0, r, cost, k_per_day, n_t, crew_cap, seed=seed)
    y_ga, obj_ga, dt_ga = solve_window_ga(dev0, r, cost, k_per_day, n_t, crew_cap, seed=seed)

    to_thb = lambda o: o / NS.OBJ_SCALE
    rows = [
        dict(solver='slsqp_rounded', objective_thb=round(to_thb(obj_slsqp)), solve_s=round(dt_slsqp, 3),
             n_cleans=int(y_slsqp_rounded.sum())),
        dict(solver='de_minlp_style', objective_thb=round(to_thb(obj_de)), solve_s=round(dt_de, 3),
             n_cleans=int(y_de.sum())),
        dict(solver='ga', objective_thb=round(to_thb(obj_ga)), solve_s=round(dt_ga, 3),
             n_cleans=int(y_ga.sum())),
    ]
    best_thb = min(r['objective_thb'] for r in rows)
    for row in rows:
        row['pct_above_best'] = (round((row['objective_thb'] - best_thb) / best_thb * 100, 2)
                                  if best_thb > 0 else 0.0)
    return rows, dict(slsqp=y_slsqp_rounded, de=y_de, ga=y_ga)


def main():
    econ = NS._load('economics.json', {})
    chist = NS._load('cleaning_history.json', {'hx': {}})
    logi = NS._load('cleaning_logistics.json', {'hx': []})

    pc = econ.get('plant_constants', {})
    feed_kbd = econ.get('feed_kbd') or 79.3
    k_per_day = pc.get('STD_ENERGY', 0.74) * feed_kbd * pc.get('NG_PRICE', 390)

    state = NS.build_hx_state(econ, chist, logi)
    online_ids = sorted([hx for hx, s in state.items() if s['online'] and s['r'] >= NS.MIN_RATE])
    r = np.array([state[hx]['r'] for hx in online_ids])
    cost = np.array([state[hx]['cost'] for hx in online_ids])
    dev0 = np.array([state[hx]['deviation0'] for hx in online_ids])

    print(f'Problem: {len(online_ids)} online-capable HX ({", ".join(online_ids)})')
    print(f'Crew cap: {NS.MAX_ONLINE_CLEANS_PER_PERIOD}/period\n')

    for n_t in (2, 4, 6):
        print(f'=== window = {n_t} periods ({n_t * NS.PERIOD_DAYS} days) ===')
        rows, _ = compare_one_window(dev0, r, cost, k_per_day, n_t, NS.MAX_ONLINE_CLEANS_PER_PERIOD)
        for row in rows:
            flag = '  <- best' if row['pct_above_best'] == 0 else f"  (+{row['pct_above_best']}% vs best)"
            print(f"  {row['solver']:16s} {row['objective_thb']:>14,} THB  "
                  f"{row['solve_s']:>7.3f}s  n_cleans={row['n_cleans']:3d}{flag}")
        print()


if __name__ == '__main__':
    main()
