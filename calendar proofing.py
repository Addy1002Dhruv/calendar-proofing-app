import calendar
import datetime
import io
import time
import fitz  # PyMuPDF
from fpdf import FPDF
from google import genai
from PIL import Image
import streamlit as st

# 1. HARDCODE YOUR GEMINI API KEY HERE
API_KEY = "YOUR_GEMINI_API_KEY"

# Streamlit Page Setup
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
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .brand-logo {
        font-size: 32px;
        font-weight: 800;
        letter-spacing: 2px;
        color: #00E5FF;
        margin: 0;
    }
    .brand-sub {
        font-size: 14px;
        color: #E0E0E0;
        margin-top: 4px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
        font-size: 16px;
        padding: 12px;
    }
</style>
<div class="main-header">
    <div class="brand-logo">📅 SMART PRINTERS — CALENDAR PROOFING</div>
    <div class="brand-sub">Automated Multi-Page Date, Day & Holiday Verification System</div>
</div>
""",
    unsafe_allow_html=True,
)


# Helper: Generate Regional Holiday Reference
def get_holiday_reference(year, region):
    if region == "None":
        return "No public holidays requested for verification."

    # Try using Python holidays library if installed, otherwise fallback to standard EA schedule
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

        formatted_list = [
            f"- {date}: {name}"
            for date, name in sorted(holiday_dict.items())
        ]
        return "\n".join(formatted_list)

    except ImportError:
        # Fallback dictionary for common fixed East African National Holidays
        base_holidays = {
            "Kenya": [
                f"{year}-01-01: New Year's Day",
                f"{year}-05-01: Labour Day",
                f"{year}-06-01: Madaraka Day",
                f"{year}-10-10: Huduma / Utamaduni Day",
                f"{year}-10-20: Mashujaa Day",
                f"{year}-12-12: Jamhuri Day",
                f"{year}-12-25: Christmas Day",
                f"{year}-12-26: Boxing Day",
            ],
            "Uganda": [
                f"{year}-01-01: New Year's Day",
                f"{year}-01-26: NRM Liberation Day",
                f"{year}-02-16: Archbishop Janani Luwum Day",
                f"{year}-03-08: International Women's Day",
                f"{year}-05-01: Labour Day",
                f"{year}-06-03: Martyrs' Day",
                f"{year}-06-09: National Heroes Day",
                f"{year}-10-09: Independence Day",
                f"{year}-12-25: Christmas Day",
                f"{year}-12-26: Boxing Day",
            ],
            "Tanzania": [
                f"{year}-01-01: New Year's Day",
                f"{year}-01-12: Zanzibar Revolution Day",
                f"{year}-04-07: Karume Day",
                f"{year}-04-26: Union Day",
                f"{year}-05-01: Labour Day",
                f"{year}-07-07: Saba Saba",
                f"{year}-08-08: Nane Nane (Farmers' Day)",
                f"{year}-10-14: Nyerere Day",
                f"{year}-12-09: Independence Day",
                f"{year}-12-25: Christmas Day",
                f"{year}-12-26: Boxing Day",
            ],
        }

        if region == "East Africa (Combined)":
            combined = []
            for k, v in base_holidays.items():
                combined.extend([f"{item} ({k})" for item in v])
            return "\n".join(sorted(combined))

        return "\n".join(
            base_holidays.get(
                region, ["No specific holiday schedule available."]
            )
        )


# High-Res Image Optimization
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


# PDF Report Generator
class CalendarQA_PDF(FPDF):

    def header(self):
        self.set_font("Arial", "B", 14)
        self.set_text_color(30, 60, 110)
        self.cell(
            0, 10, "SMART PRINTERS - CALENDAR PROOFING QA REPORT", 0, 1, "C"
        )
        self.set_draw_color(0, 122, 255)
        self.set_line_width(0.8)
        self.line(10, 20, 200, 20)
        self.ln(6)


def create_styled_calendar_pdf(overall_passed, page_results, year, region):
    pdf = CalendarQA_PDF()
    pdf.add_page()

    # Verdict Header
    if overall_passed:
        pdf.set_fill_color(34, 139, 34)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(
            0,
            12,
            f"  OVERALL VERDICT: PASSED (CALENDAR YEAR {year} APPROVED)",
            0,
            1,
            "C",
            fill=True,
        )
    else:
        pdf.set_fill_color(220, 20, 60)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(
            0,
            12,
            f"  OVERALL VERDICT: REJECTED (ERRORS FOUND IN {year} CALENDAR)",
            0,
            1,
            "C",
            fill=True,
        )

    pdf.ln(4)
    pdf.set_text_color(50, 50, 50)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(
        0, 6, f"Target Year: {year}  |  Holiday Region Target: {region}", 0, 1
    )
    pdf.ln(4)

    for res in page_results:
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(230, 238, 248)
        pdf.set_text_color(10, 50, 100)
        pdf.cell(
            0,
            7,
            f" Page {res['page_num']} Proofing Results: {res['status']}",
            0,
            1,
            "L",
            fill=True,
        )

        pdf.set_font("Arial", size=9)
        pdf.set_text_color(40, 40, 40)

        lines = res["report_text"].split("\n")
        for line in lines:
            clean_line = line.encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 5, clean_line)
        pdf.ln(3)

    return pdf.output(dest="S").encode("latin-1")


# Gemini Execution API Handler
def run_calendar_inspection(client, prompt, page_img):
    candidate_models = ["gemini-2.5-flash", "gemini-2.5-pro"]
    last_exception = None

    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name, contents=[prompt, page_img]
                )
                return response.text
            except Exception as e:
                last_exception = e
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(2)
                    continue
                else:
                    break

    raise (
        last_exception
        if last_exception
        else Exception("API temporary delay. Please retry.")
    )


# Streamlit Control Panel Controls
col1, col2 = st.columns(2)

with col1:
    target_year = st.selectbox(
        "📅 Select Target Calendar Year",
        options=[2024, 2025, 2026, 2027, 2028, 2029, 2030],
        index=2,  # Defaults to 2026
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

# PDF Ingestion
st.subheader("1. Upload Calendar Proof Document (PDF)")
pdf_file = st.file_uploader(
    "Upload multi-page or single-page calendar PDF for auditing", type=["pdf"]
)

ref_images = []
if pdf_file:
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    st.success(f"PDF loaded successfully. Total Pages/Panels: {len(doc)}")

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        ref_images.append(img)

    with st.expander("👁️ View Uploaded Calendar Pages Preview", expanded=False):
        cols = st.columns(min(len(ref_images), 4))
        for idx, img in enumerate(ref_images):
            cols[idx % 4].image(
                img, caption=f"Page {idx + 1}", use_container_width=True
            )

# Inspection Controls
st.subheader("2. Run Automated Calendar Verification")

if st.button("🚀 Execute Full Calendar Audit", type="primary"):
    if API_KEY == "YOUR_GEMINI_API_KEY":
        st.error(
            "Please update line 10 of app.py with your active Gemini API key."
        )
    elif not ref_images:
        st.error("Please upload a calendar PDF document first.")
    else:
        client = genai.Client(api_key=API_KEY)
        holiday_ref = get_holiday_reference(target_year, holiday_region)

        # Generate standard calendar metadata for reference
        cal_meta = f"TARGET YEAR: {target_year}\nTARGET HOLIDAY REGION: {holiday_region}\n\nOFFICIAL REGIONAL HOLIDAYS REFERENCE:\n{holiday_ref}"

        overall_passed = True
        page_results = []

        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, page_img_raw in enumerate(ref_images):
            page_num = idx + 1
            status_text.text(
                f"Auditing Page {page_num} of {len(ref_images)} against year {target_year} calendar rules..."
            )

            high_res_img = prepare_high_res_image(page_img_raw)

            prompt = f"""
            You are a meticulous prepress quality control auditor specializing in commercial calendar production.
            Examine this calendar page photo/proof with absolute precision for the year {target_year}.

            REFERENCE CALENDAR STANDARDS & HOLIDAY DATA:
            {cal_meta}

            AUDIT CHECKS TO EXECUTE:
            1. YEAR & MONTH VERIFICATION:
               - Is the month name spelled correctly?
               - Does the page state the correct year ({target_year})?

            2. DATE & DAY ALIGNMENT:
               - Verify every day of the month against the official calendar for {target_year}.
               - Does the 1st day of the month fall on the correct day of the week for {target_year}?
               - Does the month have the correct number of days (e.g., Feb 28/29, April 30, July 31)?
               - Are any numbers missing, duplicated, or misaligned under the weekday columns?

            3. HOLIDAYS & SPECIAL DATES:
               - Compare highlighted/red/marked dates against the target region ({holiday_region}) holidays for {target_year}.
               - Flag missing official holidays, wrong date placements, or incorrectly labeled holidays.

            4. SPELLING & PREPRESS DEFECTS:
               - Check weekday header abbreviations (Mon, Tue, Wed...).
               - Flag typos in notes, holiday labels, or artwork elements.

            REQUIRED FORMATTED OUTPUT:
            VERDICT: [PASS or FAIL]
            MONTH IDENTIFIED: [e.g. January 2026 / Not Found]
            DATE & DAY ACCURACY: [Detailed check on dates vs days of week]
            HOLIDAY AUDIT: [Verification of marked vs expected public holidays]
            ERRORS DETECTED: [Itemized list or "None detected"]
            ACTION REQUIRED: [Specific instruction for prepress operator]
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

            except Exception as e:
                overall_passed = False
                page_results.append(
                    {
                        "page_num": page_num,
                        "status": "FAIL",
                        "report_text": f"Error inspecting page {page_num}: {str(e)}",
                    }
                )

            progress_bar.progress((idx + 1) / len(ref_images))

        status_text.empty()
        st.markdown("---")
        st.subheader("📋 Master Calendar Inspection Results")

        if overall_passed:
            st.success(
                f"🟢 OVERALL VERDICT: APPROVED TO PRINT ({target_year} Calendar verification passed)"
            )
        else:
            st.error(
                f"🔴 OVERALL VERDICT: REJECTED / DISCREPANCIES DETECTED IN {target_year} CALENDAR"
            )

        for res in page_results:
            with st.expander(
                f"Page {res['page_num']} Detailed Report — {res['status']}",
                expanded=True,
            ):
                if res["status"] == "PASS":
                    st.success(res["report_text"])
                else:
                    st.error(res["report_text"])

        # Generate downloadable styled PDF report
        pdf_bytes = create_styled_calendar_pdf(
            overall_passed, page_results, target_year, holiday_region
        )
        st.download_button(
            label="📄 Download Full Calendar QA PDF Report",
            data=pdf_bytes,
            file_name=f"Calendar_Proof_Report_{target_year}_{holiday_region}.pdf",
            mime="application/pdf",
        )