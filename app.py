from flask import Flask, request, jsonify
import io
import traceback
import base64
import os
import re

from PIL import Image
import pytesseract
import fitz  # PyMuPDF

# Optional (for better OCR accuracy)
import numpy as np
import cv2

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
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))  # balance quality & speed
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)

    doc.close()
    return images


def preprocess_image(pil_img):
    """Improve OCR accuracy"""
    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
    return thresh


def extract_text_tesseract(image):
    processed = preprocess_image(image)
    text = pytesseract.image_to_string(
        processed,
        config='--oem 3 --psm 6'
    )
    return text


# ─────────────────────────────────────────────
# INVOICE EXTRACTION (basic)
# ─────────────────────────────────────────────
def extract_invoice_fields(text):
    data = {}

    # Invoice Date
    date = re.search(r"(invoice date|date)\s*[:\-]?\s*([\w\/\-.]+)", text, re.I)
    data["invoice_date"] = date.group(2) if date else None

    # Vendor
    vendor = re.search(r"(from|vendor)\s*[:\-]?\s*(.*)", text, re.I)
    data["vendor"] = vendor.group(2).strip() if vendor else None

    # Line items (basic logic)
    lines = []
    for line in text.split("\n"):
        if len(line.strip()) > 5 and any(char.isdigit() for char in line):
            lines.append(line.strip())

    data["line_items"] = lines[:20]

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
        "tesseract_installed": True
    }


@app.route('/ocr', methods=['GET', 'POST'])
def ocr():
    if request.method == 'GET':
        return {
            "message": "OCR endpoint working. Use POST request."
        }
def ocr():
    try:
        data = request.get_json()

        # Accept both Power Automate formats
        filename = data.get("filename") or data.get("file_name")
        file_base64 = data.get("file") or data.get("file_content")

        if not file_base64 or not filename:
            return jsonify({"error": "Missing filename or file"}), 400

        if not allowed_file(filename):
            return jsonify({"error": "Unsupported file type"}), 400

        file_bytes = base64.b64decode(file_base64)

        results = []

        # ───────── PDF HANDLING ─────────
        if filename.lower().endswith(".pdf"):
            images = pdf_to_images(file_bytes)

            for img in images:
                text = extract_text_tesseract(img)
                results.append(text)

            final_text = "\n\n".join(results)

        # ───────── IMAGE HANDLING ─────────
        else:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            final_text = extract_text_tesseract(img)

        # ───────── STRUCTURED DATA ─────────
        structured_data = extract_invoice_fields(final_text)

        return jsonify({
            "success": True,
            "filename": filename,
            "text": final_text,
            "structured_data": structured_data
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


# ─────────────────────────────────────────────
# RUN APP (Render compatible)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    print("\n🚀 OCR API Starting...")
    print(f"👉 Running on port: {port}")

    app.run(host="0.0.0.0", port=port)
