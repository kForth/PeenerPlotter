import json
from random import shuffle, randint, choice
from statistics import *

def pt_dist(p1, p2):
    return ((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)**0.5

def get_order_score(order):
    travel_dist = 0
    last = order[0][-1]
    for path in order[1:]:
        travel_dist += pt_dist(last, path[0])
        last = path[-1]
    return travel_dist

def randomize_order(order):
    t_order = list(order)

    # Pick a random number of paths to reverse
    num_paths_to_reverse = randint(0, len(t_order))
    if num_paths_to_reverse:
        all_paths = list(range(len(t_order)))
        for _ in range(num_paths_to_reverse):
            i = choice(all_paths)
            all_paths.remove(i)
            t_order[i] = list(reversed(t_order[i]))

    # Shuffle overall path order
    shuffle(t_order)
    return t_order

def optimize_path_order(paths, iters=1e5):
    iters = int(iters)

    print(f"Optimizing Path Order")
    print(f"n_paths={len(paths)} iters={iters}")
    best_score = get_order_score(paths)
    best_order = list(paths)
    print(f"Initial Score: {best_score}")

    for _ in range(iters):
        new_order = randomize_order(paths)
        new_score = get_order_score(new_order)

        if new_score < best_score:
            best_order = new_order
            best_score = new_score
            print(f"New Best Score: {best_score}")
    print("Done")
    return best_order

if __name__ == "__main__":
    target = 'shrek'
    with open(f'designs/{target}.json') as src:
        paths = json.load(src)
        print(f'First Score: {get_order_score(paths):0.1f}')
        
        optimized = optimize_path_order(paths, 1e6)

        with open(f'designs/{target}_optimized.json', 'w+') as out:
            json.dump(optimized, out, indent=2)

        print(f'New Best: {get_order_score(optimized):0.1f}')