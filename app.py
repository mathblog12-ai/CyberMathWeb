from flask import Flask, render_template, request, jsonify
from logic import *

app = Flask(__name__)


def clean_ineqs(items):
    out = []
    for q in items or []:
        qq = dict(q)
        qq["a"] = float(qq["a"])
        qq["b"] = float(qq["b"])
        qq["c"] = float(qq["c"])
        qq["op"] = qq["op"]
        qq["raw"] = qq.get("raw") or format_linear(qq["a"], qq["b"], qq["c"], OP_SYMBOLS[qq["op"]])
        qq["visible"] = bool(qq.get("visible", True))
        qq["color"] = qq.get("color", NEON_COLORS[len(out) % len(NEON_COLORS)])
        out.append(qq)
    return out


def objective_payload(obj):
    if not obj or not obj.get("enabled"):
        return None
    return {"a": float(obj.get("a", 1)), "b": float(obj.get("b", 1)), "F": float(obj.get("F", 0))}


def poly_json(poly):
    if not poly or len(poly) < 3:
        return None
    return [[float(x), float(y)] for x, y in poly]


def render_state(ineqs, step_idx, steps, show_vertices=False, objective=None, snap_vertex=None):
    n = len(ineqs)
    final_step = 2 * n
    traces = []
    annotations = []
    fills = []
    vertices = []

    for i, q in enumerate(ineqs):
        if not q.get("visible", True):
            continue
        line_step, shade_step = 2 * i, 2 * i + 1
        op = q["op"]
        color = q["color"]
        if op in ("<=", "<"):
            keep_side, other_side = "le", "ge"
        elif op in (">=", ">"):
            keep_side, other_side = "ge", "le"
        else:
            keep_side = other_side = None

        if step_idx >= line_step:
            pts = line_points(q)
            traces.append({
                "kind": "line", "x": [p[0] for p in pts], "y": [p[1] for p in pts],
                "color": color, "dash": "dash" if op in ("<", ">") else "solid",
                "width": 7 if step_idx == line_step else 2.0,
                "alpha": 0.22 if step_idx == line_step else 0.85,
                "name": f"d{i+1}: {q['raw']}",
            })
        if step_idx >= shade_step and keep_side:
            sat = halfplane_polygon(q["a"], q["b"], q["c"], keep_side)
            exc = halfplane_polygon(q["a"], q["b"], q["c"], other_side)
            if step_idx < final_step and sat and len(sat) >= 3:
                fills.append({"poly": poly_json(sat), "fill": color, "alpha": 0.16, "edge": color, "edge_alpha": 0.05})
            if exc and len(exc) >= 3:
                fills.append({"poly": poly_json(exc), "fill": "#000000", "alpha": 0.72, "edge": "#000000", "edge_alpha": 0})
            if step_idx == shade_step:
                tx, ty = choose_test_point(q)
                annotations.append({"x": tx, "y": ty, "text": f"M({num(tx)};{num(ty)})", "color": TEXT_COLOR})

    if n and step_idx >= final_step:
        visible = [q for q in ineqs if q.get("visible", True)]
        if visible:
            vertices = compute_polygon_vertices(ineqs)
            if len(vertices) >= 3:
                fills.append({"poly": poly_json(vertices), "fill": SOLUTION_YELLOW, "alpha": 0.50, "edge": SOLUTION_YELLOW, "edge_alpha": 1})
            else:
                region = [(DOMAIN_MIN, DOMAIN_MIN), (DOMAIN_MAX, DOMAIN_MIN), (DOMAIN_MAX, DOMAIN_MAX), (DOMAIN_MIN, DOMAIN_MAX)]
                for q in visible:
                    if q["op"] in ("<=", "<"):
                        region = clip_polygon_halfplane(region, q["a"], q["b"], q["c"], "le")
                    elif q["op"] in (">=", ">"):
                        region = clip_polygon_halfplane(region, q["a"], q["b"], q["c"], "ge")
                    if len(region) < 3:
                        break
                if len(region) >= 3:
                    fills.append({"poly": poly_json(region), "fill": SOLUTION_YELLOW, "alpha": 0.50, "edge": SOLUTION_YELLOW, "edge_alpha": 1})

    obj = objective_payload(objective)
    if obj:
        pts = line_points({"a": obj["a"], "b": obj["b"], "c": obj["F"]})
        traces.append({
            "kind": "line", "x": [p[0] for p in pts], "y": [p[1] for p in pts],
            "color": "#FF3EC9", "dash": "dashdot", "width": 2.4, "alpha": 0.95,
            "name": f"F = {format_frac(obj['a'])}x + {format_frac(obj['b'])}y = {num(obj['F'])}",
        })

        if len(vertices) >= 3 and steps and 0 <= step_idx < len(steps) and steps[step_idx]["type"] == "optimize":
            rows, mn, mx = evaluate_objective_at_vertices(vertices, obj["a"], obj["b"])
            if mn:
                annotations.append({"x": mn["x"], "y": mn["y"], "text": "MIN", "color": MIN_COLOR, "ring": MIN_COLOR})
            if mx:
                annotations.append({"x": mx["x"], "y": mx["y"], "text": "MAX", "color": MAX_COLOR, "ring": MAX_COLOR})

        if snap_vertex is not None:
            annotations.append({"x": snap_vertex[0], "y": snap_vertex[1], "text": "🔒 KHỚP ĐỈNH", "color": "#FFFFFF", "ring": SOLUTION_YELLOW, "outer": True})

    show_v = show_vertices or (steps and 0 <= step_idx < len(steps) and steps[step_idx]["type"] == "optimize")
    if show_v and len(vertices) >= 1:
        for vx, vy in vertices:
            annotations.append({"x": vx, "y": vy, "text": f"({format_frac(vx)}; {format_frac(vy)})", "color": SOLUTION_YELLOW, "vertex": True})

    return {"traces": traces, "fills": fills, "annotations": annotations, "vertices": [[float(x), float(y)] for x, y in vertices]}


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/render")
def api_render():
    data = request.get_json(force=True) or {}
    ineqs = clean_ineqs(data.get("inequalities", []))
    has_obj = bool(data.get("objective", {}).get("enabled", False))
    steps = StepEngine.generate(ineqs, has_obj)
    step_idx = int(data.get("step_idx", -1))
    step_idx = max(-1, min(step_idx, len(steps) - 1)) if steps else -1
    obj = objective_payload(data.get("objective"))
    text = ""
    if 0 <= step_idx < len(steps):
        text = StepEngine.explain(steps[step_idx], ineqs, step_idx + 1, len(steps), obj)
    else:
        text = "Nhấn “BẮT ĐẦU GIẢI” để xem\ntừng bước minh họa." if not data.get("invalidated") else "Danh sách đã thay đổi.\nNhấn “BẮT ĐẦU GIẢI” để giải lại."
    snap = data.get("snap_vertex")
    graph = render_state(ineqs, step_idx, steps, bool(data.get("show_vertices", False)), obj, snap)
    return jsonify({"steps": steps, "step_idx": step_idx, "explain": text, "graph": graph})


@app.get("/api/default")
def api_default():
    raw = ["2x + y <= 4", "x - y <= 1", "x >= 0", "y >= 0"]
    out = []
    for i, s in enumerate(raw):
        q = parse_inequality(s)
        q["raw"] = format_linear(q["a"], q["b"], q["c"], OP_SYMBOLS[q["op"]])
        q["visible"] = True
        q["color"] = NEON_COLORS[i]
        out.append(q)
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
