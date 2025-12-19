"""
Export helpers for reports - CSV, JSON, Excel formats.

Provides utilities to export report data in various formats.
"""

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, List

from app.utility.logging_client import logger


def report_to_json(report: Dict[str, Any], pretty: bool = True) -> str:
    """
    Export report to JSON format.
    
    Args:
        report: Report data dictionary
        pretty: Whether to use indentation (default: True)
        
    Returns:
        JSON string
    """
    try:
        if pretty:
            return json.dumps(report, ensure_ascii=False, indent=2, default=str)
        return json.dumps(report, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"JSON export error: {e}", component="export_helpers")
        raise ValueError(f"Failed to export to JSON: {e}") from e


def report_to_csv(report: Dict[str, Any]) -> str:
    """
    Export report findings to CSV format.
    
    Creates a CSV with columns: category, sentiment, key_points
    
    Args:
        report: Report data dictionary
        
    Returns:
        CSV string
    """
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write metadata header
        writer.writerow(["# Report Metadata"])
        writer.writerow(["Report ID", report.get("report_id", "")])
        writer.writerow(["Client Name", report.get("client_name", "")])
        writer.writerow(["INN", report.get("inn", "")])
        writer.writerow(["Created At", datetime.fromtimestamp(report.get("created_at", 0)).isoformat()])
        writer.writerow(["Risk Level", report.get("risk_level", "")])
        writer.writerow(["Risk Score", report.get("risk_score", 0)])
        writer.writerow([])
        
        # Write findings
        report_data = report.get("report_data", {})
        findings = report_data.get("findings", [])
        
        if findings:
            writer.writerow(["# Findings"])
            writer.writerow(["Category", "Sentiment", "Key Points"])
            
            for finding in findings:
                writer.writerow([
                    finding.get("category", ""),
                    finding.get("sentiment", ""),
                    finding.get("key_points", ""),
                ])
        
        # Write risk factors
        writer.writerow([])
        risk_assessment = report_data.get("risk_assessment", {})
        factors = risk_assessment.get("factors", [])
        
        if factors:
            writer.writerow(["# Risk Factors"])
            for idx, factor in enumerate(factors, 1):
                writer.writerow([f"{idx}. {factor}"])
        
        # Write recommendations
        writer.writerow([])
        recommendations = report_data.get("recommendations", [])
        
        if recommendations:
            writer.writerow(["# Recommendations"])
            for idx, rec in enumerate(recommendations, 1):
                writer.writerow([f"{idx}. {rec}"])
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"CSV export error: {e}", component="export_helpers")
        raise ValueError(f"Failed to export to CSV: {e}") from e


def reports_summary_to_csv(reports: List[Dict[str, Any]]) -> str:
    """
    Export multiple reports summary to CSV.
    
    Creates a CSV with one row per report showing key metrics.
    
    Args:
        reports: List of report dictionaries
        
    Returns:
        CSV string
    """
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Report ID",
            "Client Name",
            "INN",
            "Created At",
            "Risk Level",
            "Risk Score",
            "Findings Count",
        ])
        
        # Data rows
        for report in reports:
            report_data = report.get("report_data", {})
            findings = report_data.get("findings", [])
            
            writer.writerow([
                report.get("report_id", ""),
                report.get("client_name", ""),
                report.get("inn", ""),
                datetime.fromtimestamp(report.get("created_at", 0)).isoformat(),
                report.get("risk_level", ""),
                report.get("risk_score", 0),
                len(findings),
            ])
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"CSV summary export error: {e}", component="export_helpers")
        raise ValueError(f"Failed to export summary to CSV: {e}") from e


def normalize_report_for_export(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize report data for export.
    
    Removes internal fields and formats timestamps.
    
    Args:
        report: Raw report dictionary
        
    Returns:
        Cleaned report dictionary
    """
    try:
        cleaned = report.copy()
        
        # Format timestamps
        if "created_at" in cleaned:
            cleaned["created_at_iso"] = datetime.fromtimestamp(cleaned["created_at"]).isoformat()
        
        if "expires_at" in cleaned:
            cleaned["expires_at_iso"] = datetime.fromtimestamp(cleaned["expires_at"]).isoformat()
        
        # Remove internal fields (optional)
        # cleaned.pop("expires_at", None)
        
        return cleaned
        
    except Exception as e:
        logger.error(f"Report normalization error: {e}", component="export_helpers")
        return report


def format_bytes_size(size_bytes: int) -> str:
    """
    Format byte size to human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


__all__ = [
    "report_to_json",
    "report_to_csv",
    "reports_summary_to_csv",
    "normalize_report_for_export",
    "format_bytes_size",
]
