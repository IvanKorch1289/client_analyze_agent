from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.compat import is_versioned_request
from app.api.routes.utility import limiter, utility_router
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.utility.auth import require_admin
from app.utility.pdf_generator import save_pdf_report


def _relative_path_for(request: Request, *, route_name: str, **params: Any) -> str:
    """
    Return a URL path relative to current API root (without root_path).

    - For legacy (unversioned) routes: root_path == "" → returned path is unchanged
    - For versioned sub-app (/api/v1): root_path == "/api/v1" → strip it so clients
      that already use a versioned base URL don't end up with a double prefix.
    """
    absolute = str(request.url_for(route_name, **params))
    path = urlparse(absolute).path
    root_path = request.scope.get("root_path") or ""
    if root_path and path.startswith(root_path):
        return path[len(root_path) :] or "/"
    return path


class PDFReportRequest(BaseModel):
    """Request body for PDF report generation."""

    client_name: str
    inn: Optional[str] = None
    session_id: Optional[str] = None
    report_data: Dict[str, Any]


@utility_router.post("/reports/pdf")
async def generate_pdf_report(http_request: Request, payload: PDFReportRequest) -> Dict[str, Any]:
    """Generate PDF report from analysis data."""
    try:
        filepath = save_pdf_report(
            report_data=payload.report_data,
            client_name=payload.client_name,
            inn=payload.inn,
            session_id=payload.session_id,
        )

        filename = os.path.basename(filepath)
        return {
            "status": "success",
            "filepath": filepath,
            "filename": filename,
            "download_url": _relative_path_for(http_request, route_name="download_report", filename=filename),
        }
    except Exception as e:
        if is_versioned_request(http_request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/reports/download/{filename}")
async def download_report(filename: str):
    """Download PDF report file."""
    filepath = os.path.join("reports", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )


@utility_router.get("/reports/list")
async def list_reports(http_request: Request) -> Dict[str, Any]:
    """List all available reports."""
    reports_dir = "reports"

    if not os.path.exists(reports_dir):
        return {"status": "success", "reports": []}

    reports = []
    for filename in os.listdir(reports_dir):
        filepath = os.path.join(reports_dir, filename)
        if os.path.isfile(filepath):
            reports.append(
                {
                    "filename": filename,
                    "size_bytes": os.path.getsize(filepath),
                    "created": os.path.getctime(filepath),
                    "download_url": _relative_path_for(
                        http_request, route_name="download_report", filename=filename
                    ),
                }
            )

    reports.sort(key=lambda x: x["created"], reverse=True)

    return {"status": "success", "reports": reports, "count": len(reports)}


@utility_router.delete("/reports/{filename}")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def delete_report(request: Request, filename: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Delete a report file. Requires admin role."""
    filepath = os.path.join("reports", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        os.remove(filepath)
        return {"status": "success", "message": f"Report {filename} deleted"}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}

