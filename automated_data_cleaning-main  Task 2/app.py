import pandas as pd
import streamlit as st

from transform import clean_dataframe

st.set_page_config(
    page_title="Automated Data Cleaner",
    page_icon="🧹",
    layout="wide",
)

st.title("🧹 Automated Data Cleaning & Schema Transformation")
st.write(
    "Upload a CSV file to normalize values, handle optional nulls, "
    "remove duplicates, and validate the output schema."
)

uploaded = st.file_uploader("Upload messy CSV", type=["csv"])

if uploaded:
    try:
        raw = pd.read_csv(uploaded)

        st.subheader("1. Input preview")
        st.dataframe(raw.head(20), use_container_width=True)

        cleaned, report = clean_dataframe(raw)

        st.subheader("2. Cleaning summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Input rows", len(raw))
        c2.metric("Clean rows", len(cleaned))
        c3.metric("Rows removed", len(raw) - len(cleaned))

        st.subheader("3. Cleaned dataset")
        st.dataframe(cleaned, use_container_width=True)

        st.subheader("4. Validation log")
        st.code(report, language="text")

        st.download_button(
            "Download cleaned CSV",
            cleaned.to_csv(index=False).encode("utf-8"),
            "cleaned_output.csv",
            "text/csv",
        )
        st.download_button(
            "Download validation report",
            report.encode("utf-8"),
            "validation_report.txt",
            "text/plain",
        )
    except Exception as exc:
        st.error(f"Could not process this file: {exc}")
else:
    st.info("Upload a CSV file to begin.")

st.markdown("---")
st.markdown(
    """
    <div style="
        text-align: center;
        padding: 15px;
        background-color: #1e293b;
        border-radius: 10px;
        color: white;
    ">
        <p style="margin-bottom: 5px;">Developed By: Jay Rahane</p>
        <p style="margin: 5px;">
            📧 Email:
            <a href="mailto:jayrahane3115@gmail.com"
               style="color: #38bdf8; text-decoration: none;">
                jayrahane3115@gmail.com
            </a>
        </p>
        <p style="font-size: 12px; color: #cbd5e1;">
            Automated Data Cleaning & Schema Transformation
        </p>
        <p style="font-size: 12px; color: #94a3b8;">
            © 2026 All Rights Reserved
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
