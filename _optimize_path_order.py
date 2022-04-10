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

    # # Pick a random number of paths to split
    # num_paths_to_split = max(randint(-len(t_order), len(t_order)//2), 0)
    # split_paths = []
    # if num_paths_to_split:
    #     for _ in range(num_paths_to_split):
    #         t_path = list(choice(t_order))
    #         split_pt = randint(len(t_path)//4, len(t_path)-len(t_path)//4)
    #         t_order.remove(t_path)
    #         split_paths.append(list(t_path[:split_pt]))
    #         split_paths.append(list(t_path[split_pt:]))
    # t_order += split_paths
    
    # # Pick a random number of paths to duplicate
    # num_paths_to_duplicate = max(randint(-len(t_order), len(t_order)//2), 0)
    # duplicated_paths = []
    # if num_paths_to_duplicate:
    #     for _ in range(num_paths_to_duplicate):
    #         duplicated_paths.append(list(reversed(choice(t_order))))
    # t_order += duplicated_paths

    # Pick a random number of paths to reverse
    num_paths_to_reverse = randint(0, len(t_order))
    if num_paths_to_reverse:
        available_paths = list(range(len(t_order)))
        for _ in range(num_paths_to_reverse):
            i = choice(available_paths)
            available_paths.remove(i)
            t_order[i] = list(reversed(t_order[i]))

    # print(f'{num_paths_to_split=} {num_paths_to_duplicate=} {num_paths_to_reverse=}')

    # Shuffle overall path order
    shuffle(t_order)
    return t_order

def optimize_path_order(paths, iters=1e5):
    iters = int(iters)

    print(f"Optimizing Path Order")
    print(f"n_paths={len(paths)} iters={iters}")
    best_score = get_order_score(paths)
    best_order = list(paths)
    print(f"Initial Score: {best_score:0.1f}")

    for _ in range(iters):
        new_order = randomize_order(paths)
        new_score = get_order_score(new_order)

        if new_score < best_score:
            best_order = new_order
            best_score = new_score
            print(f"New Best Score: {best_score:0.1f}")
    print("Done")
    return best_order

if __name__ == "__main__":
    target = 'shrek'
    with open(f'designs/{target}.json') as src:
        paths = json.load(src)
        
        optimized = optimize_path_order(paths, 1e5)

        with open(f'designs/{target}_optimized.json', 'w+') as out:
            json.dump(optimized, out, indent=2)