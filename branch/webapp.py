"""The page for non-experts: bill of materials in, questions one by one, report out.

Only the page is here. What the person types is checked in forms.py; what each button does is in
interview.py, which has no page in it and is tested without a browser. build_ui() lays the page out,
one small function per panel, and connects each button to its function. Run with `python app.py`.
"""
import os
from types import SimpleNamespace

from . import __version__, connector, interview
from . import catalogue as cat
from .forms import (  # noqa: F401  (re-exported)
    COLUMNS,
    INPUT_COLUMNS,
    STAGE_WORDS,
    available_regions,
    explain_unresolved,
    inputs_from_table,
    materials,
    materials_waiting,
    missing_process_keys,
    search_text,
    spec_from_fields,
    template_fields,
    templates,
)
from .interview import (  # noqa: F401  (re-exported)
    BATCH,
    TAU,
    UNKNOWN_HINT,
    UNKNOWN_STREAK_HINT,
    finish,
    load_factors,
    load_server_factors,
    parse_answer,
    question_view,
    record_answer,
    start_session,
    status_text,
)

N_OUTPUTS = 11      # what every answer refreshes: see _outputs()


# -------------------------------------------------------------------- layout

def build_ui():
    import gradio as gr

    ctx = _context()
    with gr.Blocks(title="BRANCH: compare two products", analytics_enabled=False) as ui:
        _header(gr, ctx)
        w = SimpleNamespace(state=gr.State(None))
        _connection_panel(gr, ctx, w)
        with gr.Column(visible=True) as w.setup:
            _setup_panel(gr, ctx, w)
        with gr.Column(visible=False) as w.asking:
            _question_panel(gr, w)
        with gr.Column(visible=False) as w.done:
            _result_panel(gr, w)
        _connect(gr, ctx, w)
    return ui


def _context():
    """What the page needs to know before it is drawn: the factors, and the lists it offers."""
    try:
        factors, demo = load_server_factors()
        error = None
    except RuntimeError as exc:
        factors, demo, error = None, False, str(exc)
    return SimpleNamespace(factors=factors, demo=demo, error=error,
                           categories=interview.categories(factors),
                           templates=list(templates()), regions=available_regions(factors),
                           materials=materials(factors), waiting=materials_waiting(factors))


def _header(gr, ctx):
    gr.Markdown("# BRANCH for openLCA\nCompare two products from their bill of materials, or from processes "
                "of the openLCA database. BRANCH fills in what you do not know, asks only the questions that "
                "can change the answer, and gives you a report you can share. Free and open source. "
                f"Version {__version__}. An independent project, not affiliated with or endorsed by GreenDelta, "
                "the developer of openLCA.")
    if ctx.demo:
        gr.Markdown("**ILLUSTRATIVE NUMBERS.** This server runs on demo values, not real inventory "
                    "data. Do not use the results for decisions or claims.")
    if ctx.error:
        gr.Markdown("**Not ready yet:** BRANCH needs the impact factors of your openLCA database. "
                    "Open the **openLCA connection** panel below and press **Read factors from openLCA** "
                    "(once; it takes several minutes).")


def _connection_panel(gr, ctx, w):
    ok, msg = connector.status()
    with gr.Accordion("openLCA connection", open=bool(ctx.error) or not ok):
        have = ctx.factors is not None and not ctx.demo     # demo numbers are not the user's factors
        in_use = ("" if ctx.error or not ctx.factors else
                  f"\n\nFactors in use: `{os.path.basename(ctx.factors.get('path', 'demo'))}`.")
        w.olca_msg = gr.Markdown(msg + "\n\n" + connector.checklist_markdown(factors=have) + in_use)
        with gr.Row():
            w.check_btn = gr.Button("Check again")
            w.read_btn = gr.Button("Read factors from openLCA (once; it takes several minutes)")
        w.read_msg = gr.Markdown()


def _setup_panel(gr, ctx, w):
    w.region = gr.Dropdown(choices=ctx.regions, value=interview.default_of(ctx.regions, "PT"),
                           label="Where is it produced and sold? (type a country to search)")
    gr.Markdown("Materials: " + ", ".join(f"`{k}` ({v})" for k, v in sorted(ctx.materials.items()))
                + ("" if not ctx.waiting or ctx.demo else
                   "\n\nAlso in the catalogue, once you press **Read factors from openLCA** again: "
                   + ", ".join(ctx.waiting) + "."))
    names = ctx.templates
    w.forms = [_product_form(gr, names, side, default)
               for side, default in (("A", names[0]), ("B", names[1] if len(names) > 1 else names[0]))]
    w.service = gr.Textbox(value="", label="What do both products do? (optional, for products that are not "
                                           "containers, for example: one T-shirt worn for two years)")
    _search_box(gr, w)
    _options(gr, ctx, w)
    w.go = gr.Button("Compare", variant="primary")
    w.setup_msg = gr.Markdown()


def _product_form(gr, names, side, default):
    """The form of one product: (name, volume, refillable, bill of materials, units, other inputs)."""
    with gr.Group():
        gr.Markdown(f"### Product {side}")
        with gr.Row():
            tpl = gr.Dropdown(choices=names, value=default, label="Start from an example")
            n0, v0, r0, rows0 = template_fields(default)
            name = gr.Textbox(value=n0, label="Name")
            vol = gr.Number(value=v0, label="Content of one container (litres)")
            refill = gr.Checkbox(value=r0, label="Refillable (washed and filled again)")
        table = gr.Dataframe(value=rows0, headers=COLUMNS, datatype=["str", "str", "number"],
                             label="Bill of materials (one line per part)", interactive=True,
                             row_count=len(rows0), column_count=3)
        units = gr.Number(value=1, label="How many are needed for the same use? (1, unless the "
                                         "two products do not last or hold the same)")
        inputs = _other_inputs(gr)
        tpl.change(lambda t: template_fields(t), tpl, [name, vol, refill, table])
    return (name, vol, refill, table, units, inputs)


def _other_inputs(gr):
    with gr.Accordion("Other inputs from the openLCA database (for any product, not only containers)", open=False):
        gr.Markdown("One line per input: what it is for, the stage (material, manufacturing, "
                    "transport, use, end of life), the exact name of the openLCA process (use the "
                    "search below) and the amount for one product, in the unit the search shows. "
                    "If you do not know the amount, give the smallest and the largest it could be: "
                    "BRANCH asks you for the exact value only if it can change the answer. "
                    "For a product that is not a container, empty the bill of materials above.")
        return gr.Dataframe(value=[["", "", "", None, None]], headers=INPUT_COLUMNS,
                            datatype=["str", "str", "str", "number", "number"],
                            label="Inputs (one line per input)", interactive=True,
                            row_count=1, column_count=len(INPUT_COLUMNS))


def _search_box(gr, w):
    with gr.Accordion("Search the openLCA database (any material, energy, transport or disposal process)", open=False):
        with gr.Row():
            w.find_text = gr.Textbox(label="Words in the name of the process, for example: cotton textile")
            w.find_btn = gr.Button("Search")
        w.find_out = gr.Markdown()


def _options(gr, ctx, w):
    w.main_cat = gr.Dropdown(choices=ctx.categories, value=interview.default_of(ctx.categories, "Climate change"),
                             label="Which indicator matters most to you? (the report shows all of them)")
    rules = [("Cut-off (recycled content approach, 100:0)", "cut-off")]
    if cat.load_cff():
        rules.append(("EU Circular Footprint Formula (PEF)", "cff"))
    w.rule = gr.Radio(choices=rules, value="cut-off", label="How to count recycling")
    w.public = gr.Checkbox(value=False, label="I may use this comparison in public (marketing, labels)")


def _question_panel(gr, w):
    w.status = gr.Markdown()
    w.q_text = gr.Markdown()
    w.q_choice = gr.Radio(choices=[], label="Your answer", visible=False)
    w.q_number = gr.Number(label="Your answer", visible=False)
    with gr.Row():
        w.ok = gr.Button("Answer", variant="primary")
        w.dunno = gr.Button("I don't know (keep the default)")
        w.stop = gr.Button("Finish now (keep all the defaults)")
    w.q_msg = gr.Markdown()
    w.q_name = gr.State(None)


def _result_panel(gr, w):
    w.summary = gr.Markdown()
    w.files = gr.File(label="Reports", file_count="multiple")
    with gr.Row():
        w.send_btn = gr.Button("Send to openLCA")
        w.again = gr.Button("New comparison")
    w.backup_ok = gr.Checkbox(label="The database open in openLCA is a copy, or I have a backup of it", value=False)
    w.send_msg = gr.Markdown()


# -------------------------------------------------------------------- what the page shows after each step

def _outputs(w):
    return [w.state, w.asking, w.done, w.status, w.q_text, w.q_choice, w.q_number, w.q_name, w.summary,
            w.files, w.q_msg]


def _unchanged(gr, n=N_OUTPUTS):
    return tuple(gr.skip() for _ in range(n))


def _show(gr, s):
    """The next question, or the result when there is none: the N_OUTPUTS values of _outputs()."""
    v = question_view(s)
    if v["done"]:
        text, pdf, md = finish(s)
        return (s, gr.Column(visible=False), gr.Column(visible=True), "", "",
                gr.Radio(visible=False), gr.Number(visible=False), None, text, [pdf, md], "")
    if v["kind"] == "categorical":
        radio = gr.Radio(choices=v["options"], value=None, visible=True)
        number = gr.Number(visible=False, value=None)
    else:
        radio = gr.Radio(visible=False, choices=[])
        number = gr.Number(visible=True, value=None, label=interview.number_label(v))
    return (s, gr.Column(visible=True), gr.Column(visible=False), status_text(s),
            f"### {v['text']}{interview.question_hint(v)}", radio, number, v["name"], "", None, "")


def _bar(progress):
    """The progress callback of the connector, drawn as the progress bar of the page."""
    return lambda i, n, m: progress(i / max(n, 1), desc=f"{i}/{n} {m[:60]}")


# -------------------------------------------------------------------- the buttons
# The names on_start and on_finish are the names of the page's API (packaging/smoke_session.py).

def _start(gr):
    def on_start(reg, na, va, ra, ta, ua, ia, nb, vb, rb, tb, ub, ib, serv, main, rul, pub,
                 progress=gr.Progress()):  # noqa: B008  (how Gradio hands a progress bar to a function)
        try:
            s = interview.prepare(reg, (na, va, ra, ta, ua, ia), (nb, vb, rb, tb, ub, ib), serv, main, rul, pub,
                                  _bar(progress))
        except (ValueError, RuntimeError) as exc:
            return (gr.Column(visible=True), f"**Please check:** {exc}") + _unchanged(gr)
        return (gr.Column(visible=False), "") + _show(gr, s)
    return on_start


def _answer(gr):
    def on_answer(s, name, choice, number, unknown):
        if s is None or name is None:
            return _unchanged(gr)
        try:
            suggest_finish = interview.answer(s, name, choice, number, unknown)
        except ValueError as exc:
            return _unchanged(gr, N_OUTPUTS - 1) + (f"**{exc}**",)
        out = _show(gr, s)
        if suggest_finish and not s.done:
            out = out[:-1] + (UNKNOWN_HINT,)
        return out
    return on_answer


def _finish(gr):
    def on_finish(s):
        if s is None:
            return _unchanged(gr)
        s.finish_early()
        return _show(gr, s)
    return on_finish


def _read(gr):
    def on_read(progress=gr.Progress()):  # noqa: B008
        msg, text, regions, categories = interview.read_factors(_bar(progress))
        if regions is None:
            return msg, text, gr.skip(), gr.skip()
        return (msg, text, gr.Dropdown(choices=regions, value=interview.default_of(regions, "PT")),
                gr.Dropdown(choices=categories, value=interview.default_of(categories, "Climate change")))
    return on_read


def _connect(gr, ctx, w):
    """Each button to its function. The order is the order of the page's API."""
    outs = _outputs(w)
    answering = [w.state, w.q_name, w.q_choice, w.q_number]
    on_answer = _answer(gr)

    def on_find(text):
        return interview.search(text, ctx.demo)

    def on_check():
        return interview.connection_text()

    def on_send(s, backup_ok=False):
        return interview.send(s, backup_ok)

    w.find_btn.click(on_find, w.find_text, w.find_out)
    w.go.click(_start(gr), [w.region, *w.forms[0], *w.forms[1], w.service, w.main_cat, w.rule, w.public],
               [w.setup, w.setup_msg, *outs])
    w.ok.click(lambda s, n, c, x: on_answer(s, n, c, x, False), answering, outs, api_name="answer")
    w.dunno.click(lambda s, n, c, x: on_answer(s, n, c, x, True), answering, outs, api_name="skip")
    w.stop.click(_finish(gr), [w.state], outs)
    w.again.click(lambda: (gr.Column(visible=True), gr.Column(visible=False), None, ""), None,
                  [w.setup, w.done, w.state, w.send_msg])
    w.check_btn.click(on_check, None, w.olca_msg)
    w.read_btn.click(_read(gr), None, [w.olca_msg, w.read_msg, w.region, w.main_cat])
    w.send_btn.click(on_send, [w.state, w.backup_ok], w.send_msg)
