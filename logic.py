import re
import math
import itertools
from fractions import Fraction
import numpy as np

BG_MAIN="#121218"
BG_SIDEBAR="#181820"
BG_CARD="#1B1B26"
BG_CANVAS="#0D0D11"
GRID_COLOR="#2A2A38"
AXIS_COLOR="#71718A"
TEXT_COLOR="#E2E8F0"
TEXT_MUTED="#8A8AA0"
DANGER_COLOR="#FF5566"
NEON_COLORS=["#00F0FF","#FF007F","#00FF66","#FFA53C","#B15CFF","#39C7FF"]
SOLUTION_YELLOW="#FFE600"
MIN_COLOR="#00FF66"
MAX_COLOR="#FFA53C"
OP_SYMBOLS={"<=":"≤",">=":"≥","<":"<",">":">","=":"="}
OP_SYMBOL_TO_INTERNAL={v:k for k,v in OP_SYMBOLS.items()}
XMIN,XMAX=-10,10
YMIN,YMAX=-10,10
DOMAIN_MIN,DOMAIN_MAX=-30,30
GRID_RES=500
ZOOM_MIN_SPAN=0.8
ZOOM_MAX_SPAN=55
SNAP_TOLERANCE=0.01

# =============================================================================
# 1. BẢNG MÀU (THEME & COLOR PALETTE)
# =============================================================================
BG_MAIN        = "#121218"   # Nền ứng dụng chính
BG_SIDEBAR     = "#181820"   # Nền sidebar (hơi sáng hơn nền chính)
BG_CARD        = "#1B1B26"   # Nền các thẻ / card
BG_CANVAS      = "#0D0D11"   # Nền vùng đồ thị
GRID_COLOR     = "#2A2A38"   # Lưới
AXIS_COLOR     = "#71718A"   # Trục tọa độ
TEXT_COLOR     = "#E2E8F0"   # Chữ trắng băng giá
TEXT_MUTED     = "#8A8AA0"
DANGER_COLOR   = "#FF5566"

NEON_COLORS = ["#00F0FF", "#FF007F", "#00FF66", "#FFA53C", "#B15CFF", "#39C7FF"]
SOLUTION_YELLOW = "#FFE600"
MIN_COLOR = "#00FF66"
MAX_COLOR = "#FFA53C"

# Ký hiệu toán học hiển thị cho người dùng (không bao giờ hiện "<=" / ">=")
OP_SYMBOLS = {"<=": "≤", ">=": "≥", "<": "<", ">": ">", "=": "="}
OP_SYMBOL_TO_INTERNAL = {v: k for k, v in OP_SYMBOLS.items()}

XMIN, XMAX = -10, 10          # Khung nhìn (view) mặc định khi khởi động
YMIN, YMAX = -10, 10
DOMAIN_MIN, DOMAIN_MAX = -30, 30  # Miền tính toán rộng hơn để hỗ trợ Zoom/Pan
GRID_RES = 500                 # Độ phân giải lưới numpy dùng để tô miền nghiệm
ZOOM_MIN_SPAN = 0.8             # Không cho phóng to quá gần
ZOOM_MAX_SPAN = 55              # Không cho thu nhỏ vượt quá miền domain
SNAP_TOLERANCE = 0.01           # Khoảng cách (đơn vị trục) để đường F "khớp" vào đỉnh


# =============================================================================
# 2. LOGIC TOÁN HỌC (PARSING & GIẢI HỆ BPT)
# =============================================================================
class ParseError(Exception):
    """Lỗi cú pháp khi người dùng nhập bất phương trình sai định dạng."""
    pass


def _parse_coef(coef_str: str) -> float:
    """Chuyển chuỗi hệ số (có thể là phân số 'a/b') sang float."""
    if "/" in coef_str:
        num_s, _, den_s = coef_str.partition("/")
        num_v = float(num_s) if num_s not in ("", ".") else 1.0
        if den_s in ("", "."):
            raise ParseError(f"Thiếu mẫu số trong phân số '{coef_str}'.")
        den_v = float(den_s)
        if den_v == 0:
            raise ParseError("Mẫu số của phân số không được bằng 0.")
        return num_v / den_v
    return float(coef_str)


def _parse_linear_expr(expr: str) -> dict:
    """Phân tích một biểu thức bậc nhất dạng 'ax + by + c' thành dict hệ số."""
    expr = expr.replace(" ", "")
    if expr == "":
        return {"x": 0.0, "y": 0.0, "c": 0.0}
    if expr[0] not in "+-":
        expr = "+" + expr
    terms = re.findall(r"[+-][^+-]+", expr)
    if not terms or "".join(terms) != expr:
        raise ParseError(f"Biểu thức không hợp lệ: '{expr}'")

    result = {"x": 0.0, "y": 0.0, "c": 0.0}
    for term in terms:
        sign = -1.0 if term[0] == "-" else 1.0
        body = term[1:]
        if body == "":
            raise ParseError(f"Số hạng rỗng gần: '{term}'")
        # Tách biến (x hoặc y) khỏi phần hệ số, cho phép phân số ở bất kỳ vị
        # trí nào: '1/2x', 'x/2', '2x/3', '3/4' đều hợp lệ.
        var_match = re.search(r"[xy]", body)
        if var_match:
            var = var_match.group()
            coef_str = body[:var_match.start()] + body[var_match.end():]
        else:
            var = ""
            coef_str = body
        if not re.match(r"^\d*\.?\d*(?:/\d*\.?\d*)?$", coef_str):
            raise ParseError(f"Không thể phân tích số hạng: '{term}'")
        if coef_str == "" and var == "":
            raise ParseError(f"Số hạng không xác định: '{term}'")
        coef = _parse_coef(coef_str) if coef_str else 1.0
        if var == "x":
            result["x"] += sign * coef
        elif var == "y":
            result["y"] += sign * coef
        else:
            result["c"] += sign * coef
    return result


def parse_inequality(text: str) -> dict:
    """
    Chuyển một chuỗi người dùng nhập (vd: '2x + y <= 3') thành dạng chuẩn:
        a*x + b*y  [op]  c
    Trả về dict {'a', 'b', 'c', 'op', 'raw'}.
    """
    raw = text.strip()
    if not raw:
        raise ParseError("Vui lòng nhập một bất phương trình.")

    m = re.search(r"(<=|>=|<|>|=)", raw)
    if not m:
        raise ParseError("Thiếu dấu so sánh (<=, >=, <, >, =).")

    op = m.group(1)
    left_str, right_str = raw[:m.start()], raw[m.end():]

    try:
        left = _parse_linear_expr(left_str)
        right = _parse_linear_expr(right_str)
    except ParseError:
        raise
    except Exception as exc:  # bảo vệ chống crash với input lạ
        raise ParseError(f"Cú pháp không hợp lệ: {exc}")

    a = left["x"] - right["x"]
    b = left["y"] - right["y"]
    c = right["c"] - left["c"]

    if abs(a) < 1e-9 and abs(b) < 1e-9:
        raise ParseError("Bất phương trình phải chứa biến x hoặc y.")

    return {"a": a, "b": b, "c": c, "op": op, "raw": raw}


def format_linear(a: float, b: float, c: float, op: str = "=") -> str:
    """Định dạng 'ax + by [op] c' cho đẹp mắt, bỏ hệ số 0/1 thừa.

    `op` mặc định là dấu "=" (dùng để hiển thị PHƯƠNG TRÌNH đường biên), nhưng
    có thể truyền vào một ký hiệu toán học khác (≤, ≥, <, >) để hiển thị
    chính BẤT PHƯƠNG TRÌNH — không bao giờ dùng chuỗi kiểu "<=" / ">=".
    """
    def fmt_term(coef, var):
        if abs(coef) < 1e-9:
            return None
        r = round(coef, 4)
        if r == int(r):
            r = int(r)
        if r == 1:
            return var
        if r == -1:
            return f"-{var}"
        return f"{r}{var}"

    tx, ty = fmt_term(a, "x"), fmt_term(b, "y")
    parts = []
    if tx:
        parts.append(tx)
    if ty:
        if parts:
            parts.append(("+ " + ty) if not ty.startswith("-") else ("- " + ty[1:]))
        else:
            parts.append(ty)
    if not parts:
        parts = ["0"]
    cr = round(c, 4)
    if cr == int(cr):
        cr = int(cr)
    return f"{' '.join(parts)} {op} {cr}"


def num(v):
    """Làm gọn số để hiển thị (bỏ .0 nếu là số nguyên)."""
    v = round(v, 4)
    return int(v) if v == int(v) else v


def format_frac(v, max_denominator=1000):
    """Định dạng một số để hiển thị: trả về số nguyên nếu v là số nguyên,
    ngược lại trả về dạng PHÂN SỐ tối giản (vd: '3/2', '-7/3') thay vì số
    thập phân dài dòng — giúp tọa độ đỉnh dễ đọc và chính xác hơn."""
    r = round(v, 6)
    if abs(r - round(r)) < 1e-6:
        return str(int(round(r)))
    frac = Fraction(r).limit_denominator(max_denominator)
    if frac.denominator == 1:
        return str(frac.numerator)
    sign = "-" if frac.numerator < 0 else ""
    return f"{sign}{abs(frac.numerator)}/{frac.denominator}"


def is_satisfied(ineq: dict, x, y):
    """Kiểm tra điểm/mảng (x, y) có thỏa mãn bất phương trình không (vector hóa)."""
    val = ineq["a"] * x + ineq["b"] * y
    op = ineq["op"]
    if op == "<=":
        return val <= ineq["c"] + 1e-9
    if op == ">=":
        return val >= ineq["c"] - 1e-9
    if op == "<":
        return val < ineq["c"] - 1e-9
    if op == ">":
        return val > ineq["c"] + 1e-9
    return np.abs(val - ineq["c"]) < 1e-6  # '='


def choose_test_point(ineq: dict):
    """Chọn điểm thử, ưu tiên gốc tọa độ O(0,0) nếu nó không nằm trên đường thẳng."""
    for (x, y) in [(0, 0), (1, 0), (0, 1), (2, 3), (1, 1), (-1, 2)]:
        if abs(ineq["a"] * x + ineq["b"] * y - ineq["c"]) > 1e-6:
            return x, y
    return 5, 7


def clip_polygon_halfplane(poly, a, b, c, keep):
    """Cắt một đa giác LỒI `poly` (danh sách đỉnh (x, y)) bằng nửa mặt
    phẳng a*x + b*y <= c (nếu keep='le') hoặc a*x + b*y >= c (nếu
    keep='ge'), dùng thuật toán Sutherland–Hodgman.

    Vì đây là phép cắt HÌNH HỌC bằng giao điểm thực sự (không dựa vào
    lưới numpy rời rạc), biên kết quả luôn là các đoạn thẳng chính xác,
    áp sát tuyệt đối vào đường biên thật — không bị răng cưa/bậc thang
    như khi tô màu bằng contourf trên lưới.
    """
    if not poly:
        return []

    def inside(p):
        val = a * p[0] + b * p[1]
        return val <= c + 1e-9 if keep == "le" else val >= c - 1e-9

    def intersect(p1, p2):
        v1 = a * p1[0] + b * p1[1] - c
        v2 = a * p2[0] + b * p2[1] - c
        if abs(v1 - v2) < 1e-12:
            return p2
        t = v1 / (v1 - v2)
        return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))

    output = []
    n = len(poly)
    for i in range(n):
        curr, prev = poly[i], poly[i - 1]
        curr_in, prev_in = inside(curr), inside(prev)
        if curr_in:
            if not prev_in:
                output.append(intersect(prev, curr))
            output.append(curr)
        elif prev_in:
            output.append(intersect(prev, curr))
    return output


def halfplane_polygon(a, b, c, keep, bound=None):
    """Trả về đa giác là phần giao giữa hình chữ nhật miền tính toán
    (mặc định [DOMAIN_MIN, DOMAIN_MAX]^2, hoặc `bound` nếu truyền vào)
    với nửa mặt phẳng a*x + b*y <= c (keep='le') hay >= c (keep='ge')."""
    rect = bound or [(DOMAIN_MIN, DOMAIN_MIN), (DOMAIN_MAX, DOMAIN_MIN),
                      (DOMAIN_MAX, DOMAIN_MAX), (DOMAIN_MIN, DOMAIN_MAX)]
    return clip_polygon_halfplane(rect, a, b, c, keep)


def line_points(ineq: dict, xlim=(DOMAIN_MIN, DOMAIN_MAX), ylim=(DOMAIN_MIN, DOMAIN_MAX)):
    """Trả về 2 điểm để vẽ đường thẳng biên trong phạm vi khung nhìn."""
    a, b, c = ineq["a"], ineq["b"], ineq["c"]
    x0, x1 = xlim
    y0, y1 = ylim
    if abs(b) > 1e-9:
        return [(x0, (c - a * x0) / b), (x1, (c - a * x1) / b)]
    xv = c / a
    return [(xv, y0), (xv, y1)]


def compute_polygon_vertices(inequalities, tol=1e-6):
    """Tìm các đỉnh của đa giác miền nghiệm cuối cùng.

    Cách làm: lấy giao điểm của mọi cặp đường biên, giữ lại những giao điểm
    thỏa mãn ĐỒNG THỜI toàn bộ hệ bất phương trình (đang hiển thị), sau đó
    sắp xếp chúng theo góc quanh trọng tâm để tạo thành một đa giác lồi khép
    kín đúng thứ tự (dùng để vẽ/nối các đỉnh theo đúng biên).
    """
    active = [q for q in inequalities if q.get("visible", True)]
    pts = []
    for i, j in itertools.combinations(range(len(active)), 2):
        a1, b1, c1 = active[i]["a"], active[i]["b"], active[i]["c"]
        a2, b2, c2 = active[j]["a"], active[j]["b"], active[j]["c"]
        det = a1 * b2 - a2 * b1
        if abs(det) < tol:
            continue  # hai đường song song hoặc trùng nhau -> bỏ qua
        x = (c1 * b2 - c2 * b1) / det
        y = (a1 * c2 - a2 * c1) / det

        ok = True
        for q in active:
            val = q["a"] * x + q["b"] * y
            op = q["op"]
            if op == "<=" and val > q["c"] + 1e-6:
                ok = False
            elif op == ">=" and val < q["c"] - 1e-6:
                ok = False
            elif op == "<" and val >= q["c"] - 1e-6:
                ok = False
            elif op == ">" and val <= q["c"] + 1e-6:
                ok = False
            elif op == "=" and abs(val - q["c"]) > 1e-4:
                ok = False
            if not ok:
                break
        if ok:
            pts.append((x, y))

    # Loại các điểm trùng nhau do sai số dấu phẩy động
    uniq = []
    for p in pts:
        if not any(abs(p[0] - u[0]) < 1e-6 and abs(p[1] - u[1]) < 1e-6 for u in uniq):
            uniq.append(p)

    if len(uniq) < 3:
        return uniq  # có thể là 0, 1 hoặc 2 đỉnh (miền rỗng / nửa đường thẳng)

    cx = sum(p[0] for p in uniq) / len(uniq)
    cy = sum(p[1] for p in uniq) / len(uniq)
    uniq.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return uniq


def evaluate_objective_at_vertices(vertices, a, b):
    """Tính F = a*x + b*y tại từng đỉnh, trả về danh sách
    [{'x', 'y', 'F'}] và (vertex_min, vertex_max) kèm giá trị F tương ứng."""
    rows = [{"x": vx, "y": vy, "F": a * vx + b * vy} for (vx, vy) in vertices]
    if not rows:
        return rows, None, None
    row_min = min(rows, key=lambda r: r["F"])
    row_max = max(rows, key=lambda r: r["F"])
    return rows, row_min, row_max


class StepEngine:
    """Sinh ra danh sách các bước minh họa (line -> test -> ... -> conclusion)."""

    @staticmethod
    def generate(inequalities, has_objective=False):
        steps = []
        for i, ineq in enumerate(inequalities):
            steps.append({"type": "line", "idx": i})
            steps.append({"type": "test", "idx": i})
        if inequalities:
            steps.append({"type": "conclusion"})
            # Nếu người dùng đã bật đường mức F, thêm bước cuối cùng để
            # tính F tại từng đỉnh của đa giác nghiệm và chốt min/max.
            if has_objective:
                steps.append({"type": "optimize"})
        return steps

    @staticmethod
    def explain(step, inequalities, step_no, total, objective=None):
        header = f"BƯỚC {step_no}/{total}\n" + "─" * 26 + "\n"
        if step["type"] == "line":
            i = step["idx"]
            ineq = inequalities[i]
            strict = ineq["op"] in ("<", ">")
            style = "nét đứt (không lấy dấu bằng)" if strict else "nét liền (có dấu bằng)"
            return (header +
                    f"Vẽ đường thẳng biên d{i + 1} của bất phương trình "
                    f"({ineq['raw']}):\n\n"
                    f"    d{i + 1}:  {format_linear(ineq['a'], ineq['b'], ineq['c'])}\n\n"
                    f"Đường được vẽ bằng {style}, màu neon đại diện cho BPT {i + 1}.")
        if step["type"] == "test":
            i = step["idx"]
            ineq = inequalities[i]
            tx, ty = choose_test_point(ineq)
            val = ineq["a"] * tx + ineq["b"] * ty
            ok = is_satisfied(ineq, tx, ty)
            side = "CHỨA điểm thử" if ok else "KHÔNG chứa điểm thử"
            return (header +
                    f"Chọn điểm thử M({num(tx)}; {num(ty)}) (không nằm trên d{i + 1}).\n\n"
                    f"Thay vào vế trái:\n"
                    f"    {num(ineq['a'])}×{num(tx)} + {num(ineq['b'])}×{num(ty)} = {num(val)}\n\n"
                    f"So sánh: {num(val)} {OP_SYMBOLS[ineq['op']]} {num(ineq['c'])}  →  "
                    f"{'ĐÚNG ✓' if ok else 'SAI ✗'}\n\n"
                    f"=> Miền nghiệm của BPT {i + 1} là nửa mặt phẳng {side}. "
                    f"Nửa mặt phẳng được CHỌN sẽ sáng màu hơn (ánh màu neon riêng), "
                    f"nửa còn lại bị loại bỏ và phủ ĐEN VĨNH VIỄN (không mờ dần, "
                    f"không đổi khi sang bước sau).")
        if step["type"] == "optimize":
            return StepEngine._explain_optimize(header, inequalities, objective)
        # conclusion
        return (header +
                "KẾT LUẬN\n\n"
                "Miền nghiệm của cả hệ là phần GIAO NHAU của tất cả các miền nghiệm "
                "riêng lẻ. Vùng này được làm sáng rực rỡ bằng màu VÀNG NEON trên đồ "
                "thị, khớp chính xác với đường biên của đa giác — đây chính là tập "
                "hợp mọi điểm (x, y) thỏa mãn ĐỒNG THỜI toàn bộ hệ bất phương trình. "
                "Bấm \"📐 Hiện đỉnh\" để xem tọa độ các đỉnh của đa giác nghiệm này.")

    @staticmethod
    def _explain_optimize(header, inequalities, objective):
        """Sinh nội dung giải thích bước tối ưu: bảng F tại từng đỉnh + kết
        luận min/max bằng lời."""
        if not objective:
            return (header +
                    "TỐI ƯU HÀM MỤC TIÊU F = ax + by\n\n"
                    "Chưa có hàm mục tiêu nào được áp dụng. Hãy nhập hệ số a, b rồi "
                    "bấm \"📈 Hiện đường mức F\" ở mục 4 trong sidebar.")

        vertices = compute_polygon_vertices(inequalities)
        a, b = objective["a"], objective["b"]
        obj_str = format_linear(a, b, 0, "=").rsplit(" = ", 1)[0]

        if len(vertices) < 3:
            return (header +
                    f"TỐI ƯU HÀM MỤC TIÊU F = {obj_str}\n\n"
                    "Miền nghiệm KHÔNG BỊ CHẶN (không phải một đa giác kín), nên không "
                    "thể liệt kê đầy đủ các đỉnh để so sánh. Tùy theo hướng của F, giá "
                    "trị F có thể tiến ra vô cực (không tồn tại min hoặc max hữu hạn "
                    "trên toàn miền).")

        rows, row_min, row_max = evaluate_objective_at_vertices(vertices, a, b)

        # --- Bảng F tại từng đỉnh (canh cột bằng font Consolas) ---
        table_lines = [f"{'Đỉnh (x; y)':<16}{'F = ' + obj_str:<14}"]
        table_lines.append("-" * 30)
        for r in rows:
            point_str = f"({format_frac(r['x'])}; {format_frac(r['y'])})"
            mark = ""
            if r is row_min:
                mark = " ← min"
            if r is row_max:
                mark = " ← max" if mark == "" else mark + " / max"
            table_lines.append(f"{point_str:<16}{str(num(r['F'])):<8}{mark}")
        table_str = "\n".join(table_lines)

        min_point = f"({format_frac(row_min['x'])}; {format_frac(row_min['y'])})"
        max_point = f"({format_frac(row_max['x'])}; {format_frac(row_max['y'])})"

        narrative = (
            f"Vì miền nghiệm là một đa giác LỒI và BỊ CHẶN, giá trị nhỏ nhất và lớn "
            f"nhất của F = {obj_str} (nếu có) chỉ có thể đạt được TẠI MỘT TRONG CÁC "
            f"ĐỈNH của đa giác — không cần kiểm tra các điểm khác bên trong miền.\n\n"
            f"Lần lượt thay tọa độ từng đỉnh vào F rồi so sánh các kết quả:\n\n"
            f"{table_str}\n\n"
            f"So sánh {len(rows)} giá trị F ở trên:\n"
            f"  • F NHỎ NHẤT (min) = {num(row_min['F'])}  tại đỉnh {min_point}\n"
            f"  • F LỚN NHẤT  (max) = {num(row_max['F'])}  tại đỉnh {max_point}\n\n"
            f"=> Kết luận: min F = {num(row_min['F'])} tại {min_point}; "
            f"max F = {num(row_max['F'])} tại {max_point}."
        )

        return header + f"TỐI ƯU HÀM MỤC TIÊU F = {obj_str}\n\n" + narrative


