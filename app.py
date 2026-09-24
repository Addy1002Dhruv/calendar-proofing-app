import calendar
import datetime
import io
import time
from PIL import Image
import fitz  # PyMuPDF
import streamlit as st
from google import genai
from fpdf import FPDF

# Active Gemini API Key
API_KEY = "AQ.Ab8RN6LEK3tLGxCapMfvEyuy2ke7tcTU7WypnSJM160F-xtzzw"

st.set_page_config(
    page_title="Smart Printers - Calendar Proofing QA",
    layout="wide",
    page_icon="📅",
)

st.markdown(
    """
<style>
    .main-header {
        background: linear-gradient(90deg, #1E3C72 0%, #2A5298 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
        text-align: center;
    }
    .brand-logo { font-size: 32px; font-weight: 800; color: #00E5FF; }
    .brand-sub { font-size: 14px; color: #E0E0E0; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; font-size: 16px; padding: 12px; }
</style>
<div class="main-header">
    <div class="brand-logo">📅 SMART PRINTERS — CALENDAR PROOFING</div>
    <div class="brand-sub">Automated Multi-Page Date, Day & Holiday Verification System</div>
</div>
""",
    unsafe_allow_html=True,
)


def get_holiday_reference(year, region):
    if region == "None":
        return "No public holidays requested for verification."
    try:
        import holidays

        holiday_dict = {}
        if region in ["Kenya", "East Africa (Combined)"]:
            holiday_dict.update(
                {
                    str(d): f"{n} (Kenya)"
                    for d, n in holidays.KE(years=year).items()
                }
            )
        if region in ["Uganda", "East Africa (Combined)"]:
            holiday_dict.update(
                {
                    str(d): f"{n} (Uganda)"
                    for d, n in holidays.UG(years=year).items()
                }
            )
        if region in ["Tanzania", "East Africa (Combined)"]:
            holiday_dict.update(
                {
                    str(d): f"{n} (Tanzania)"
                    for d, n in holidays.TZ(years=year).items()
                }
            )
        return "\n".join([f"- {d}: {n}" for d, n in sorted(holiday_dict.items())])
    except ImportError:
        return f"Standard major holidays enabled for {region} ({year})."


def prepare_high_res_image(image, max_dim=3200):
    img = image.copy()
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=93)
    buffer.seek(0)
    return Image.open(buffer)


class CalendarQA_PDF(FPDF):

    def header(self):
        self.set_font("Arial", "B", 14)
        self.set_text_color(30, 60, 110)
        self.cell(
            0, 10, "SMART PRINTERS - CALENDAR PROOFING QA REPORT", 0, 1, "C"
        )
        self.line(10, 20, 200, 20)
        self.ln(6)


def create_styled_calendar_pdf(overall_passed, page_results, year, region):
    pdf = CalendarQA_PDF()
    pdf.add_page()
    pdf.set_fill_color(
        (34, 139, 34) if overall_passed else (220, 20, 60)
    )
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(
        0,
        12,
        f" OVERALL VERDICT: {'PASSED' if overall_passed else 'REJECTED'}",
        0,
        1,
        "C",
        fill=True,
    )
    pdf.ln(4)

    for res in page_results:
        pdf.set_font("Arial", "B", 11)
        pdf.set_text_color(10, 50, 100)
        pdf.cell(
            0,
            7,
            f" Page {res['page_num']} Proofing Results: {res['status']}",
            0,
            1,
            "L",
        )
        pdf.set_font("Arial", size=9)
        pdf.set_text_color(40, 40, 40)
        for line in res["report_text"].split("\n"):
            pdf.multi_cell(
                0, 5, line.encode("latin-1", "replace").decode("latin-1")
            )
        pdf.ln(3)

    return pdf.output(dest="S").encode("latin-1")


def run_calendar_inspection(client, prompt, page_img):
    candidate_models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
    last_exception = None

    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name, contents=[prompt, page_img]
            )
            return response.text
        except Exception as e:
            last_exception = e
            continue

    raise last_exception if last_exception else Exception("API Call Failed")


col1, col2 = st.columns(2)
with col1:
    target_year = st.selectbox(
        "📅 Select Target Calendar Year",
        options=[2024, 2025, 2026, 2027, 2028, 2029, 2030],
        index=2,
    )
with col2:
    holiday_region = st.selectbox(
        "🌍 Select Public Holiday Region",
        options=[
            "None",
            "Kenya",
            "Uganda",
            "Tanzania",
            "East Africa (Combined)",
        ],
        index=1,
    )

st.subheader("1. Upload Calendar Proof Document (PDF)")
pdf_file = st.file_uploader("Upload calendar PDF", type=["pdf"])

ref_images = []
if pdf_file:
    try:
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        st.success(f"PDF loaded ({len(doc)} pages detected)")
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ref_images.append(img)
    except Exception as pdf_err:
        st.error(f"Failed to read PDF file: {str(pdf_err)}")

st.subheader("2. Run Automated Calendar Verification")
if st.button("🚀 Execute Full Calendar Audit", type="primary"):
    if not ref_images:
        st.error("Please upload a valid calendar PDF file first.")
    else:
        try:
            client = genai.Client(api_key=API_KEY)
            holiday_ref = get_holiday_reference(target_year, holiday_region)
            cal_meta = f"TARGET YEAR: {target_year}\nHOLIDAY REGION: {holiday_region}\nHOLIDAYS:\n{holiday_ref}"

            overall_passed = True
            page_results = []
            progress_bar = st.progress(0)

            for idx, page_img_raw in enumerate(ref_images):
                page_num = idx + 1
                high_res_img = prepare_high_res_image(page_img_raw)
                prompt = f"""
                You are a senior print QA auditor. Examine this calendar page for {target_year}.
                {cal_meta}
                Checks:
                1. Verify spelling of month and weekday names.
                2. Check date alignment against day of week for {target_year}.
                3. Check highlighted holidays for {holiday_region}.
                Format response clearly with VERDICT: PASS or FAIL.
                """

                try:
                    report_text = run_calendar_inspection(
                        client, prompt, high_res_img
                    )
                    page_passed = (
                        "PASS" in report_text.upper()
                        and "FAIL" not in report_text.upper()
                    )
                    if not page_passed:
                        overall_passed = False
                    page_results.append(
                        {
                            "page_num": page_num,
                            "status": "PASS" if page_passed else "FAIL",
                            "report_text": report_text,
                        }
                    )
                except Exception as audit_err:
                    overall_passed = False
                    st.error(
                        f"API Call Failed on Page {page_num}: {str(audit_err)}"
                    )
                    page_results.append(
                        {
                            "page_num": page_num,
                            "status": "FAIL",
                            "report_text": f"Error: {str(audit_err)}",
                        }
                    )

                progress_bar.progress((idx + 1) / len(ref_images))

            st.markdown("---")
            if overall_passed:
                st.success(
                    f"🟢 OVERALL VERDICT: PASSED ({target_year} Calendar Approved)"
                )
            else:
                st.error(f"🔴 OVERALL VERDICT: REJECTED (Discrepancies found)")

            for res in page_results:
                with st.expander(
                    f"Page {res['page_num']} Report — {res['status']}"
                ):
                    st.write(res["report_text"])

            pdf_bytes = create_styled_calendar_pdf(
                overall_passed, page_results, target_year, holiday_region
            )
            st.download_button(
                "📄 Download Audit Report PDF",
                data=pdf_bytes,
                file_name="Calendar_Audit_Report.pdf",
                mime="application/pdf",
            )
        except Exception as global_err:
            st.error(f"Application Error: {str(global_err)}")