from flask import Flask, request, jsonify
import io
import traceback
import base64

from PIL import Image
import pytesseract
import fitz  
import re

app = Flask(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'pdf', 'webp'}


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def pdf_to_images(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)

    doc.close()
    return images

def extract_text(image):
    return pytesseract.image_to_string(image)

# ─────────────────────────────────────────────
# INVOICE EXTRACTION (basic)

def extract_invoice_fields(text):
    data = {}

    # Invoice Date
    date = re.search(r"(invoice date|date)\s*[:\-]?\s*([\w\/\-\.]+)", text, re.I)
    data["invoice_date"] = date.group(2) if date else None

    # Vendor
    vendor = re.search(r"(from|vendor)\s*[:\-]?\s*(.*)", text, re.I)
    data["vendor"] = vendor.group(2).strip() if vendor else None

    # Line items (simple heuristic)
    lines = []
    for line in text.split("\n"):
        if len(line.strip()) > 5 and any(char.isdigit() for char in line):
            lines.append(line.strip())

    data["line_items"] = lines[:20]  # limit

    return data


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return {
        "status": "OCR API Running",
        "endpoints": {
            "/ocr": "POST file for OCR",
            "/health": "GET health check"
        }
    }


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "pytesseract": True
    }


@app.route("/ocr", methods=["POST"])
def ocr():
    try:
        # -------------------------
        # Case 1: file upload
        # -------------------------
        if "file" in request.files:
            file = request.files["file"]
            filename = file.filename

            if not allowed_file(filename):
                return jsonify({"error": "Invalid file type"}), 400

            file_bytes = file.read()

        # -------------------------
        # Case 2: base64 (Power Automate)
        # -------------------------
        else:
            data = request.json
            filename = data.get("filename", "file.pdf")
            file_bytes = base64.b64decode(data["file"])

        ext = filename.rsplit(".", 1)[1].lower()

        # -------------------------
        # Convert to images
        # -------------------------
        if ext == "pdf":
            images = pdf_to_images(file_bytes)
        else:
            images = [Image.open(io.BytesIO(file_bytes)).convert("RGB")]

        # -------------------------
        # OCR PROCESS
        # -------------------------
        full_text = ""

        for img in images:
            text = extract_text(img)
            full_text += text + "\n"

        # -------------------------
        # EXTRACT INVOICE FIELDS
        # -------------------------
        structured = extract_invoice_fields(full_text)

        return jsonify({
            "success": True,
            "filename": filename,
            "text": full_text,
            "structured_data": structured
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ─────────────────────────────────────────────
# RUN APP
# ─────────────────────────────────────────────
# if __name__ == "__main__":
#     print("\n🚀 OCR API Running at http://localhost:5000")
#     print("👉 POST file to /ocr")
#     print("👉 GET health at /health\n")

#     app.run(host="0.0.0.0", port=5000, debug=True)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    print("\n🚀 OCR API Starting on Render...")
    print(f"👉 Running on port: {port}")

    app.run(host="0.0.0.0", port=port)
