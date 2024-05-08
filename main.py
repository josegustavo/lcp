# -*- coding: utf-8 -*-
import random
import json
from lcp.src.problems.problems import Problems
from lcp.src.algorithm import Population, GeneticAlgorithm
from lcp.src.algorithm.population import GroupImprovement
from concurrent.futures import ProcessPoolExecutor

import multiprocessing

types_count = [5, 10, 15, 20]

for i in types_count:
    random.seed(100)
    Problems(file_path='problems/types_%d.json' % i)\
        .generate(25, N_TYPES=i, BOX_SIDE_MIN=250, BOX_SIDE_MAX=750)

improvements = [GroupImprovement.none,
                GroupImprovement.during,
                GroupImprovement.late_all,
                GroupImprovement.late_best,
                GroupImprovement.late_some]

random.seed(42)


def solve(args):
    problem, imp, num_types = args
    random.seed(problem.id)  # usar la misma semilla para cada problema

    population = Population(problem)
    individuals = population.generate_random_individuals(100)
    population.individuals = individuals
    population.evaluate()
    first_best_fitness = population.best.fitness

    if imp != GroupImprovement.none:
        population = Population(problem, imp)
        population.individuals = individuals
        population.evaluate()

    ga = GeneticAlgorithm(population=population,
                          MAX_DURATION=150,
                          P_MUT_GEN=1/num_types,
                          )
    ga.start(first_best_fitness)
    return ga.stats


def main():
    with ProcessPoolExecutor(max_workers=4) as executor:
        args = []
        for i in types_count:
            problems = Problems(file_path='problems/types_%d.json' %
                                i).load_problems()
            for problem in problems:
                num_types = len(problem.box_types)
                args += [(problem, imp, num_types) for imp in improvements]
        # print("Cantidad de problemas a resolver: %s" % len(args))
        results = executor.map(solve, args)

        for result in results:
            with open('results.txt', 'a') as outfile:
                json.dump(result, outfile)
                outfile.write('\n')
            print("\rProblema resuelto: %s" % result['problem_id'])


if __name__ == "__main__":
    main()
