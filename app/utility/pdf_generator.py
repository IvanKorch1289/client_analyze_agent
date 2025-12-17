"""
PDF report generator for client analysis reports.

Generates PDF documents from analysis results with support for
Russian text and structured report formatting.
"""

import io
import os
from datetime import datetime
from typing import Any, Dict, Optional

from fpdf import FPDF

from app.utility.logging_client import logger


class ReportPDF(FPDF):
    """
    Custom PDF class for generating analysis reports.
    
    Supports Russian text through DejaVu font and provides
    structured formatting for risk assessments and findings.
    """
    
    def __init__(self):
        """Initialize PDF with A4 format and UTF-8 support."""
        super().__init__()
        self.add_page()
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        """Add page header with title."""
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 10, "Client Analysis Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        
    def footer(self):
        """Add page footer with page number."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def add_title(self, title: str):
        """
        Add main title to the report.
        
        Args:
            title: Title text.
        """
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        
    def add_section(self, title: str):
        """
        Add section header.
        
        Args:
            title: Section title.
        """
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 8, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        
    def add_text(self, text: str):
        """
        Add paragraph text.
        
        Args:
            text: Paragraph content.
        """
        self.set_font("Helvetica", "", 10)
        safe_text = text.encode("latin-1", errors="replace").decode("latin-1")
        self.multi_cell(0, 5, safe_text)
        self.ln(2)
        
    def add_key_value(self, key: str, value: str):
        """
        Add key-value pair line.
        
        Args:
            key: Label.
            value: Value.
        """
        self.set_font("Helvetica", "B", 10)
        self.cell(50, 6, f"{key}:", new_x="RIGHT")
        self.set_font("Helvetica", "", 10)
        safe_value = str(value).encode("latin-1", errors="replace").decode("latin-1")
        self.cell(0, 6, safe_value, new_x="LMARGIN", new_y="NEXT")
        
    def add_risk_score(self, score: int, level: str):
        """
        Add risk score with visual indicator.
        
        Args:
            score: Risk score 0-100.
            level: Risk level (low, medium, high, critical).
        """
        colors = {
            "low": (46, 204, 113),
            "medium": (241, 196, 15),
            "high": (230, 126, 34),
            "critical": (231, 76, 60),
        }
        color = colors.get(level, (128, 128, 128))
        
        self.set_font("Helvetica", "B", 14)
        self.cell(50, 10, "Risk Score:", new_x="RIGHT")
        
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.cell(30, 10, f"{score}/100", fill=True, align="C", new_x="RIGHT")
        
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "I", 12)
        self.cell(0, 10, f"  ({level.upper()})", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        
    def add_findings(self, findings: list):
        """
        Add list of findings.
        
        Args:
            findings: List of finding strings.
        """
        self.set_font("Helvetica", "", 10)
        for i, finding in enumerate(findings, 1):
            safe_finding = finding.encode("latin-1", errors="replace").decode("latin-1")
            self.multi_cell(0, 5, f"{i}. {safe_finding}")
            self.ln(1)


def generate_analysis_pdf(
    report_data: Dict[str, Any],
    client_name: str,
    inn: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bytes:
    """
    Generate PDF report from analysis data.
    
    Args:
        report_data: Analysis report dictionary containing risk score,
                    findings, recommendations, and citations.
        client_name: Name of the analyzed client/company.
        inn: Company INN (optional).
        session_id: Analysis session ID (optional).
        
    Returns:
        bytes: PDF file content as bytes.
    """
    pdf = ReportPDF()
    
    pdf.add_title(f"Analysis Report: {client_name}")
    
    pdf.add_section("General Information")
    pdf.add_key_value("Client", client_name)
    if inn:
        pdf.add_key_value("INN", inn)
    if session_id:
        pdf.add_key_value("Session ID", session_id)
    pdf.add_key_value("Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    pdf.ln(5)
    
    risk_score = report_data.get("risk_score", 0)
    risk_level = report_data.get("risk_level", "unknown")
    pdf.add_section("Risk Assessment")
    pdf.add_risk_score(risk_score, risk_level)
    
    if report_data.get("summary"):
        pdf.add_section("Summary")
        pdf.add_text(report_data["summary"])
    
    findings = report_data.get("findings", [])
    if findings:
        pdf.add_section("Findings")
        pdf.add_findings(findings)
    
    recommendations = report_data.get("recommendations", [])
    if recommendations:
        pdf.add_section("Recommendations")
        pdf.add_findings(recommendations)
    
    citations = report_data.get("citations", [])
    if citations:
        pdf.add_section("Sources")
        for cite in citations[:10]:
            safe_cite = str(cite).encode("latin-1", errors="replace").decode("latin-1")
            pdf.add_text(f"- {safe_cite}")
    
    return pdf.output()


def save_pdf_report(
    report_data: Dict[str, Any],
    client_name: str,
    output_dir: str = "reports",
    inn: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """
    Generate and save PDF report to file.
    
    Args:
        report_data: Analysis report dictionary.
        client_name: Name of the analyzed client/company.
        output_dir: Directory to save the PDF.
        inn: Company INN (optional).
        session_id: Analysis session ID (optional).
        
    Returns:
        str: Path to the saved PDF file.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in client_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{safe_name}_{timestamp}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    pdf_bytes = generate_analysis_pdf(report_data, client_name, inn, session_id)
    
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    
    logger.info(f"PDF report saved: {filepath}", component="pdf")
    return filepath
