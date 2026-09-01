# CyberMath Web

Phiên bản web của app **CyberMath: Hệ BPT 2 Ẩn**.

## Chạy trên máy

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Mở: `http://127.0.0.1:5000`

## Đưa lên Render

1. Tạo repository GitHub và upload toàn bộ thư mục này.
2. Vào Render → New → Web Service → chọn repository.
3. Render có thể dùng `render.yaml`; nếu nhập thủ công:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. Deploy.

Không cần cài CustomTkinter/Tkinter/Matplotlib trên máy chủ. Thuật toán toán học cốt lõi của file CyberMath được giữ ở `logic.py`; `original_desktop/cybermath_app.py` là bản desktop gốc để đối chiếu.
