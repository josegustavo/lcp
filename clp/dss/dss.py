from copy import deepcopy
from math import ceil, floor, pi
from pathlib import Path
import asyncio
import random
from typing import List
from click import Group
import cufflinks as cf
from htmltools import p
from matplotlib import pyplot as plt
import pandas as pd
import yfinance as yf
from faicons import icon_svg
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinywidgets import output_widget, render_plotly, register_widget
from containers import containers_list, containers
from clp.src.algorithm import chromosome
from clp.src.algorithm.chromosome import Chromosome, Improvement
from clp.src.algorithm.gene import Gene
from clp.src.algorithm.genetic_algorithm import GeneticAlgorithm
from clp.src.algorithm.population import GroupImprovement, Population
from clp.src.container.box_type import BoxType
from clp.src.container.container import Container
from clp.src.graphic.draw_container import draw
from clp.src.problems.problem import Problem


app_dir = Path(__file__).parent

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_selectize("container", "Contenedor",
                           choices=containers_list),
        ui.output_ui("input_length_ui"),
        # ui.input_numeric("length", "Length (mm)", value=0),
        # ui.input_numeric("width", "Width (mm)", value=0),
        # ui.input_numeric("height", "Height (mm)", value=0),
        # Peso que puede soportar
        # ui.input_numeric("max_weight", "Peso máximo (kg)", value=0),
        ui.input_slider("time", "Tiempo de ejecución (s)",
                        min=10, max=300, value=60),

        ui.input_task_button("btn", "Procesar", label_busy="Procesando..."),
        ui.input_action_button("btn_cancel", "Cancelar"),
    ),
    ui.layout_column_wrap(
        ui.value_box(
            "Valor actual",
            ui.output_ui("price"),
            showcase=icon_svg("dollar-sign"),
        ),
        ui.value_box(
            "Cambio",
            ui.output_ui("change"),
            showcase=ui.output_ui("change_icon"),
        ),
        ui.value_box(
            "Porcentaje de llenado",
            ui.output_ui("fill_percent"),
            showcase=icon_svg("percent"),
        ),
        fill=False,
    ),
    ui.layout_columns(
        ui.navset_tab(
            ui.nav_panel("Configuración",
                         ui.div(id="main-content"),
                         ui.input_action_button(
                             "btn_add_box_type", "Agregar nuevo")
                         ),
            ui.nav_panel("Evolución de mejora",
                         ui.card(
                             ui.output_plot("improvement_log"),
                             full_screen=True,
                         ),
                         ),
            ui.nav_panel("Disposición Final",
                         ui.card(
                             ui.output_plot("containers_result"),
                             full_screen=True,
                         ),
                         )
        ),

        ui.card(
            ui.card_header("Orden Final"),
            ui.output_data_frame("latest_data"),
        ),
        col_widths=[9, 3],
    ),
    ui.include_css(app_dir / "styles.css"),
    title="DSS Cargo",
    fillable=True,
)


def server(input: Inputs, output: Outputs, session: Session):

    result_algorithm = reactive.value([])
    result_improvement = reactive.value([])
    row_count = reactive.value(0)

    @reactive.calc
    def get_change():
        change = 0
        res = get_result_algorithm()
        if res:
            first, last = res[0], res[-1],
            change = last.cost_value - first.cost_value
        return change

    @reactive.calc
    def get_change_percent():
        percent = 0
        if get_result_algorithm():
            chromosome = get_result_algorithm()[-1]
            percent = 100*chromosome.occupation_ratio

        return percent

    @reactive.calc
    def get_result_algorithm():
        res = []
        b = input.btn_add_box_type()

        if result_algorithm.get():
            res = result_algorithm.get()
        else:
            box_types = []

            for i in range(1, b+1):
                if not input["t%s_l" % i]():
                    print(['NO L', i])
                    continue
                l = input["t%s_l" % i]()
                h = input["t%s_h" % i]()
                w = input["t%s_w" % i]()
                weight = input["t%s_weight" % i]()
                value = input["t%s_value" % i]()
                max_count = input["t%s_max_count" % i]()
                box = BoxType(l, w, h, i, 0, max_count, value, weight)
                box_types.append(box)
            print(['GENES', box_types])
            genes = [Gene(type=b, box_count=b.max_count, rotation=0)
                     for b in box_types if b]
            container = Container(
                input.length(), input.width(), input.height())
            c = Chromosome(genes=genes, container=container)
            c.evaluate(Improvement.during)
            res = [c]

        return res

    @render.ui
    def price():
        cost_value = 0
        if get_result_algorithm():
            chromosome = get_result_algorithm()[-1]
            cost_value = chromosome.cost_value

        return "{:,.2f}".format(cost_value)

    @render.ui
    def change():
        return "${:,.2f}".format(get_change())

    @render.ui
    def change_icon():
        change = get_change()
        icon = icon_svg("arrow-up" if change >= 0 else "arrow-down")
        icon.add_class(f"text-{('success' if change >= 0 else 'danger')}")
        return icon

    @render.ui
    def fill_percent():
        return f"{get_change_percent():.2f}%"

    @render.plot
    def containers_result():
        pieces = []
        if get_result_algorithm():
            pieces = get_result_algorithm()[-1].result

        container = Container(input.length(), input.width(), input.height())
        fig = draw(pieces, container_dimension=container)
        return fig

    @render.plot
    def improvement_log():
        fig, ax = plt.subplots(dpi=100)
        if result_improvement.get():
            x = result_improvement.get()
            ax.plot(x)

        return fig

    @render.data_frame
    def latest_data():
        genes = []
        if get_result_algorithm():
            genes = [('T%s' % (g.type.type), g.box_count, 'Sí' if g.rotation else 'No')
                     for g in get_result_algorithm()[-1].genes if g.box_count > 0]
            genes += [('Total', sum([g.box_count for g in get_result_algorithm()[-1].genes]), '')]
        result = pd.DataFrame(genes, columns=["Tipo", "Cantidad", "Rotación"])
        return render.DataGrid(result)

    @ui.bind_task_button(button_id="btn")
    @reactive.extended_task
    async def slow_compute(problem: Problem, MAX_DURATION: int, improvements: List[int], history: List[Chromosome]) -> None:
        population = Population(problem, GroupImprovement.during)

        individuals = population.generate_random_individuals(
            99 if len(history) > 0 else 100)
        if len(history) > 0:
            individuals.append(deepcopy(history[-1]))
        population.individuals = individuals

        population.evaluate()
        first_best_fitness = population.best.fitness
        ga = GeneticAlgorithm(population=population,
                              MAX_DURATION=MAX_DURATION,
                              P_MUT_GEN=1/len(problem.box_types),
                              )
        ga.start(first_best_fitness)
        result_improvement.set(improvements+ga.stats['best_values'])
        result_algorithm.set(history+[ga.population.best])

    @reactive.effect
    @reactive.event(input.btn, ignore_none=False)
    def handle_click():
        container = Container(input.length(),
                              input.width(),
                              input.height())
        box_types = []
        b = input.btn_add_box_type()
        print(['BBBBBBBBBBB', b])
        for i in range(1, b+1):
            if not input["t%s_l" % i]():
                continue
            l = input["t%s_l" % i]()
            h = input["t%s_h" % i]()
            w = input["t%s_w" % i]()
            weight = input["t%s_weight" % i]()
            value = input["t%s_value" % i]()
            max_count = input["t%s_max_count" % i]()
            box = BoxType(l, w, h, i, 0, max_count, value, weight)
            box_types.append(box)
        problem = Problem("1", container, box_types)

        slow_compute(problem, input.time(),
                     result_improvement.get(),
                     get_result_algorithm())

    @reactive.effect
    @reactive.event(input.btn_cancel)
    def handle_cancel():
        slow_compute.cancel()

    @render.text
    def show_result():
        return str(slow_compute.result())

    @output
    @render.ui
    def input_length_ui():
        selected = input.container()
        l, w, h, v, weight = containers[selected][:5]
        result = [
            ui.input_numeric("length", "Largo (mm)", value=round(l*1000)),
            ui.input_numeric("width", "Ancho (mm)", value=round(w*1000)),
            ui.input_numeric("height", "Alto (mm)", value=round(h*1000)),
            ui.input_numeric("max_weight", "Peso máximo (kg)", value=round(1000*weight, 1))]
        return result

    @reactive.effect
    def _():
        i = input.btn_add_box_type()
        with reactive.isolate():
            container_l, container_w, container_h = input.length(), input.width(), input.height()
            ml = (container_l//random.randint(250, 600))
            mw = (container_w//random.randint(250, 600))
            l = floor(container_l/ml)
            w = floor(container_w/mw)
            if random.randint(0, 1):
                l, w = w, l
            h = floor(container_h/(container_h//random.randint(250, 600)))
            v_box = l*w*h
            v_container = container_l*container_w*container_h/10
            count_box = ceil(v_container/v_box)
            row = ui.layout_columns(
                ui.input_numeric(
                    "t%s_l" % i, "Largo (mm)" if i == 1 else None, value=l),
                ui.input_numeric(
                    "t%s_w" % i, "Ancho (mm)" if i == 1 else None, value=w),
                ui.input_numeric(
                    "t%s_h" % i, "Alto (mm)" if i == 1 else None, value=h),
                ui.input_numeric(
                    "t%s_weight" % i, "Peso (kg)" if i == 1 else None, value=round(random.uniform(5, 10), 2)),
                ui.input_numeric(
                    "t%s_value" % i, "Valor ($)" if i == 1 else None, value=random.randint(10, 100)),
                ui.input_numeric(
                    "t%s_max_count" % i, "Cant     Máx" if i == 1 else None, value=count_box),
            )
            ui.insert_ui(
                ui.div({"id": "inserted-row-%s" % i}, row),
                selector="#main-content",
                where="beforeEnd",
            )
        row_count.set(i)
        # elif btn > 0:
        #    ui.remove_ui("#inserted-slider")


app = App(app_ui, server, debug=True)