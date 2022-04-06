import json
from random import shuffle, randint, choice
from statistics import *

def pt_dist(p1, p2):
    return ((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)**0.5

def get_order_score(order):
    travel_pts = []
    last = order[0][-1]
    for path in order[1:]:
        travel_pts.append([last, path[0]])
        last = path[-1]

    score = sum([pt_dist(*pts) for pts in travel_pts])
    return score

def randomize_order(order):
    # Pick a random number of paths to reverse
    num_paths_to_reverse = randint(0, len(order))
    if num_paths_to_reverse:
        all_paths = list(range(len(order)))
        for _ in range(num_paths_to_reverse):
            i = choice(all_paths)
            all_paths.remove(i)
            order[i] = list(reversed(order[i]))

    # Shuffle overall path order
    shuffle(order)
    
    return order

with open('designs/smiley_face.json') as src:
    paths = json.load(src)
    best_score = get_order_score(paths)
    best_order = paths
    
    print(f"first_score={best_score}")

    for i in range(int(1e6)):
        t_paths = list(best_order)
        randomize_order(t_paths)
        score = get_order_score(t_paths)
        if score < best_score:
            best_score = score
            best_order = t_paths
            with open("designs/temp.json", "w+") as out:
                json.dump(best_order, out, indent=2)

            print(f"New Best: {best_score}")