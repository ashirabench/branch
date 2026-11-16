"""Manager report: one PDF in plain English (Step 7).

For a manager, not an LCA practitioner: the answer in one sentence, how sure
BRANCH is, where the impact comes from (with disposal on its own), what would
change the answer, what the person told BRANCH and what BRANCH assumed, and
the ISO 14044 notice on public comparisons, which is always printed.

    from branch.manager_report import manager_pdf
    manager_pdf(result, model, "outputs/report.pdf", public=False)
"""
import datetime as _dt
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

from .agent import ISO_PUBLIC_NOTICE  # noqa: E402
from .help import fmt_pct, is_percent, percent_question, plural  # noqa: E402
from .whatif import indicators, reversals, stages  # noqa: E402

GREEN, AMBER, INK, MUTED = "#2f6b4f", "#c17a2b", "#1f2328", "#5b636b"
STAGE_LABELS = {"material": "Making the packaging", "supply_transport": "Shipping packaging to the filler",
                "transport": "Delivery to shops", "washing": "Washing and refilling",
                "end_of_life": "Disposal (end of life)"}
STAGE_ORDER = ["material", "manufacturing", "supply_transport", "transport", "washing", "use", "end_of_life", "other"]
# Plain words for the stages of products described by inputs from the database (builder STAGES).
ANY_PRODUCT_LABELS = {"material": "Materials", "manufacturing": "Manufacturing", "transport": "Transport",
                      "use": "Use", "end_of_life": "Disposal (end of life)", "other": "Other inputs"}


def _uses_region(meta):
    """The rules for containers read the region (electricity, legs, national priors). A product described
    only by processes chosen from the database does not: its processes carry their own location."""
    return any(p.get("components") for p in meta.get("products", []))


def _stage_labels(meta):
    """Containers keep their own words; products without a bill of materials use the general ones."""
    containers = any(p.get("components") for p in meta.get("products", []))
    return {**ANY_PRODUCT_LABELS, **STAGE_LABELS} if containers else {**STAGE_LABELS, **ANY_PRODUCT_LABELS}


def _unit(category):
    from .indicators import unit
    return unit(category)


def _num(x):
    if x == 0:
        return "0"
    if abs(x) >= 100:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


def _who(decided_by, source):
    if decided_by == "human":
        return "You"
    kind = "published source" if source.startswith("SOURCE") else "assumption"
    if decided_by.startswith("human: don't know"):
        return f"You did not know: default ({kind})"
    if decided_by == "given before the session":
        return "Your bill of materials"
    return f"Default ({kind})"


def _shown(choice, x):
    """A number of this choice as the person sees it: shares in percent, as in the questions."""
    if not isinstance(x, float):
        return str(x)
    return f"{x * 100:.3g}%" if is_percent(choice.name) else _num(x)


def _value(choice, result):
    if choice.name in result["fixed"]:
        return _shown(choice, choice.decode(result["fixed"][choice.name]))
    if choice.kind != "continuous":
        return "one of: " + ", ".join(choice.labels)
    lo, hi = choice._frozen().ppf([0.05, 0.95])
    return f"likely {_shown(choice, float(lo))} to {_shown(choice, float(hi))}"


def _plain_question(choice):
    text = choice.question or choice.name
    return percent_question(text) if is_percent(choice.name) else text


def _chart(model, st, unit):
    labels = list(st)
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=200)
    left = [0.0] * len(labels)
    palette = {"material": "#9fb8ad", "manufacturing": "#c3b8d6", "supply_transport": "#c9d6cf",
               "transport": "#d9d4c7", "washing": "#b7c4d6", "use": "#b7c4d6", "end_of_life": AMBER}
    words = _stage_labels(getattr(model, "meta", {}))
    stage_keys = [k for k in STAGE_ORDER if any(k in s for s in st.values())]
    stage_keys += sorted({k for s in st.values() for k in s} - set(stage_keys))
    for k in stage_keys:
        vals = [max(st[lab].get(k, 0.0), 0.0) for lab in labels]
        ax.barh(labels, vals, left=left, color=palette.get(k, "#cccccc"), edgecolor="white",
                label=words.get(k, k.replace("_", " ")))
        left = [a + b for a, b in zip(left, vals)]
    ax.invert_yaxis()
    ax.set_xlabel(f"{unit} per functional unit (average)", fontsize=8, color=MUTED)
    ax.tick_params(labelsize=8, colors=INK)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def manager_pdf(result, model, path, public=None, company=None):
    """Write the manager report to path (PDF). Returns path."""
    meta = getattr(model, "meta", {})
    unit = _unit(meta.get("category"))
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=18, leading=22, alignment=0, textColor=INK)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, leading=16, textColor=GREEN, spaceBefore=10)
    P = ParagraphStyle("P", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=INK)
    SMALL = ParagraphStyle("S", parent=P, fontSize=8, leading=10.5, textColor=MUTED)
    BIG = ParagraphStyle("B", parent=P, fontSize=12.5, leading=17)
    BOX = ParagraphStyle("X", parent=P, fontSize=9, leading=12.5)

    a, b = model.label_a, model.label_b
    (ma, _, _), (mb, _, _) = result["impacts"][a], result["impacts"][b]
    low, high = (a, b) if result.get("verdict_a_lower", ma < mb) else (b, a)
    m_low, m_high = result["impacts"][low][0], result["impacts"][high][0]
    pct = (m_high - m_low) / m_high * 100 if m_high else 0.0
    sure = (1 - result["p_flip"]) * 100
    sure_txt = "more than 99%" if sure > 99 else f"{sure:.0f}%"

    story = []
    if model.factor_data.get("demo") if hasattr(model, "factor_data") else False:
        story += [Table([[Paragraph("<b>ILLUSTRATIVE NUMBERS.</b> This report uses demo values, not real "
                                    "inventory data. Do not use it for any decision or claim.", BOX)]],
                        colWidths=[17 * cm],
                        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fde7e7")),
                                          ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#b42318")),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 8)])), Spacer(1, 8)]
    story += [Paragraph(f"{a} or {b}?", H1),
             Paragraph(f"Environmental comparison for {company + ', ' if company else ''}"
                       f"{meta.get('region_path', meta.get('country', '')) if _uses_region(meta) else 'the processes chosen from the database'}. "
                       f"Functional unit: {meta.get('functional_unit', '')}. "
                       f"Indicator: {meta.get('category', '')}. "
                       f"Prepared by BRANCH on {_dt.date.today():%d %B %Y}.", SMALL),
             Spacer(1, 10)]

    if result["certified"]:
        answer = (f"<b>{low}</b> has the lower impact: on average about <b>{pct:.0f}% less</b> than "
                  f"{high} ({_num(m_low)} versus {_num(m_high)} {unit}). BRANCH is "
                  f"<b>{sure_txt} confident</b> in this conclusion.")
    else:
        answer = (f"<b>Not settled yet.</b> {low} looks lower on average ({_num(m_low)} versus "
                  f"{_num(m_high)} {unit}), but BRANCH is only {sure:.0f}% confident, below its "
                  f"{fmt_pct(1 - result['tau'])} threshold. Answering the questions you skipped, "
                  f"or replacing the assumptions listed below, can settle it.")
    story += [Table([[Paragraph(answer, BIG)]], colWidths=[17 * cm],
                    style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4f0")),
                                      ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(GREEN)),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                      ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])),
              Spacer(1, 4),
              Paragraph(f"BRANCH asked you {plural(result['questions'], 'question')} and filled in the rest "
                        f"from data and documented defaults. Every choice is listed at the end.", SMALL)]

    st = stages(model, result)
    story += [Paragraph("Where the impact comes from", H2), Image(_chart(model, st, unit), width=17 * cm,
                                                                    height=6.1 * cm)]
    eol = []
    for lab in (a, b):
        tot = sum(st[lab].values())
        share = st[lab].get("end_of_life", 0.0) / tot * 100 if tot else 0.0
        shown = "under 1%" if 0 <= share < 1 else f"about {share:.0f}%"
        eol.append(f"{lab}: disposal is <b>{shown}</b> of its impact")
    containers = any(p.get("components") for p in meta.get("products", []))
    rest = ("The rest comes from making, shipping and (for refillables) washing the packaging"
            if containers else "The rest comes from the other stages shown in the chart")
    story.append(Paragraph("How much disposal matters. " + "; ".join(eol) + f". {rest}, which is why BRANCH always "
                           "looks at the whole life cycle.", P))

    if hasattr(model, "build_args"):
        rows_ind = indicators(model, result)
        if len(rows_ind) > 1:
            story.append(Paragraph("All environmental indicators", H2))
            flips = [r for r in rows_ind if not r["agrees"]]
            if flips:
                story.append(Paragraph(
                    f"<b>Trade off.</b> The answer above is for {meta.get('category')}. On "
                    + ", ".join(r["name"].lower() for r in flips[:6])
                    + (" and others" if len(flips) > 6 else "")
                    + ", the other option is lower. Decide which indicators matter most for you; "
                      "ISO 14044 does not allow adding them into one score for a public comparison.", P))
            else:
                story.append(Paragraph("The same option is lower on every indicator below.", P))
            rows = [["Indicator", a, b, "Lower", "Confidence"]]
            for r in rows_ind:
                conf = max(r["p_a_lower"], 1 - r["p_a_lower"]) * 100
                rows.append([Paragraph(f"{r['name']}<br/><font size=6.5 color='{MUTED}'>{r['unit']}</font>", SMALL),
                             _num(r["mean_a"]), _num(r["mean_b"]), Paragraph(r["lower"], SMALL),
                             "more than 99%" if conf > 99 else f"{conf:.0f}%"])
            story.append(_table(rows, [5.6 * cm, 2.6 * cm, 2.6 * cm, 3.6 * cm, 2.6 * cm]))

    story.append(Paragraph("What would change the answer", H2))
    rev = reversals(model, result)
    if rev:
        story.append(Paragraph("The smallest change in a single item that would make the other option the "
                               "better one, with everything else as it is now:", P))
        rows = [["Item", "Now", "Answer flips at"]]
        for r in rev:
            c = model.by_name[r["name"]]
            rows.append([Paragraph(_plain_question(c), SMALL), _shown(c, r["now"]), _shown(c, r["reverses_at"])])
        story.append(_table(rows, [11 * cm, 2.8 * cm, 3.2 * cm]))
    else:
        story.append(Paragraph("No single item, within its plausible range, changes the answer. "
                               "The conclusion is robust.", P))

    story.append(Paragraph("What you told BRANCH, and what it assumed", H2))
    rows = [["Item", "Value", "Decided by"]]
    for c in model.choices:
        if not c.askable:                          # the database's own uncertainty is not an item anyone decided
            continue
        rows.append([Paragraph(_plain_question(c), SMALL), Paragraph(_value(c, result), SMALL),
                     Paragraph(_who(result["decided_by"][c.name], c.source), SMALL)])
    story.append(_table(rows, [10.2 * cm, 3.6 * cm, 3.2 * cm]))
    assumed = [c for c in model.choices if c.source.startswith("ASSUMPTION") and c.name not in result["fixed"]]
    gaps = meta.get("sources_needed", [])
    if assumed or gaps:
        txt = (f"{len(assumed)} default(s) above are still assumptions rather than published data (marked "
               f"\"assumption\" in the last column). The technical report names the document and year behind "
               f"every published default. " if assumed else "")
        if gaps:
            txt += "Data still to be sourced for this region: " + "; ".join(gaps) + "."
        story.append(Paragraph(txt, SMALL))

    notice = ISO_PUBLIC_NOTICE if public else (
        "If you plan to use this comparison in marketing or in any other public claim: ISO 14044 requires "
        "a critical review by a panel of independent interested parties for comparative assertions "
        "disclosed to the public. BRANCH follows ISO 14040 and ISO 14044 and prepares the study for that "
        "review, but it does not replace the panel of reviewers.")
    story.append(KeepTogether([
        Paragraph("Before using this result in public", H2),
        Table([[Paragraph(notice, BOX)]], colWidths=[17 * cm],
              style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbf0e2")),
                                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(AMBER)),
                                ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))]))

    story += [Paragraph("About this report", H2),
              Paragraph("Method: attributional life cycle assessment following ISO 14040 and ISO 14044 "
                        "(ILCD Situation A), "
                        + ("Circular Footprint Formula of the EU Product Environmental Footprint for recycling "
                           "(Annex C parameters; energy recovery credits not included)."
                           if meta.get("system_model") == "cff" else "cut-off approach for recycling.")
                        + " Uncertain items are treated as "
                        "ranges and propagated by Monte Carlo simulation; the confidence above is the share "
                        "of simulations that agree with the conclusion. Averages above are per functional unit.",
                        SMALL),
              Paragraph(f"Data: {meta.get('citation') or 'see factors file'}. Impact method: "
                        f"{meta.get('method')}. Software: BRANCH (open source, MPL 2.0) with openLCA.", SMALL)]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=f"{a} or {b}? BRANCH report", author="BRANCH")
    doc.build(story)
    return path


def _table(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(INK)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(GREEN)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t
