import io
import json
import random
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.pdfgen import canvas
import qrcode
from PIL import Image as PILImage, ImageDraw, ImageFont
from faker import Faker
from backend.app.mock_issuers.router import (
    register_mock_issuer_record,
    ISSUER_UNI,
    ISSUER_STATE_NOC,
    ISSUER_NBA,
    ISSUER_SUB_REGISTRAR,
    ISSUER_TER_PAY
)

fake = Faker('en_IN')

# Numbered canvas to draw page numbers and footer headers
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        # Header rule
        self.setStrokeColor(colors.HexColor("#003366"))
        self.setLineWidth(1)
        self.line(40, 800, 555, 800)
        # Footer rule & text
        self.setStrokeColor(colors.HexColor("#CCCCCC"))
        self.line(40, 45, 555, 45)
        self.drawString(45, 32, "TruthTrace Verification Prototype • AICTE APH Regulatory Schema Compliant")
        self.drawRightString(550, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def create_qr_image_bytes(payload_dict: dict) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=2,
    )
    qr.add_data(json.dumps(payload_dict, sort_keys=True, separators=(',', ':')))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class DocumentGenerator:
    @staticmethod
    def generate_affidavit_pdf(
        inst_name: str,
        pid: str,
        trustee_name: str,
        affidavit_date: str = "2026-02-15"
    ) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=45, rightMargin=45, topMargin=55, bottomMargin=55)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'AffidavitTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            textColor=colors.HexColor("#8B0000"),
            spaceAfter=12
        )
        body_style = ParagraphStyle(
            'AffidavitBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            spaceAfter=10
        )
        bold_body = ParagraphStyle(
            'AffidavitBold',
            parent=body_style,
            fontName='Helvetica-Bold'
        )

        elements = [
            Spacer(1, 10),
            Paragraph("NON-JUDICIAL STAMP PAPER • GOVERNMENT OF INDIA", ParagraphStyle('Stamp', fontName='Helvetica-Bold', fontSize=10, alignment=1, textColor=colors.HexColor("#003366"))),
            Paragraph("e-Stamp Certificate No: IN-DL90812481029314Y", ParagraphStyle('SubStamp', fontName='Helvetica', fontSize=9, alignment=1, textColor=colors.HexColor("#444444"))),
            Spacer(1, 15),
            Paragraph("OMNIBUS AFFIDAVIT IN AICTE PRESCRIBED FORMAT", title_style),
            Paragraph(f"<b>Permanent Institute ID (PID):</b> {pid}", bold_body),
            Paragraph(f"<b>Institution:</b> {inst_name}", bold_body),
            Paragraph(f"<b>Executed on:</b> {affidavit_date}", bold_body),
            Spacer(1, 8),
            Paragraph(f"I, <b>{trustee_name}</b>, Chairman/Secretary of the Educational Trust running <b>{inst_name}</b> (PID: {pid}), do hereby solemnly affirm and state on oath as under:", body_style),
            Paragraph("1. That the technical campus complies fully with all norms stipulated in the AICTE Approval Process Handbook (APH §2.1.4).", body_style),
            Paragraph("2. That all required land, instructional carpet area, administrative and amenities facilities are held in unencumbered possession.", body_style),
            Paragraph("3. That no anti-ragging complaints, financial malpractice, or statutory state deficiencies are pending against the institution.", body_style),
            Paragraph("<b>द्विभाषी अभिसाक्ष्य (Bilingual Declarative Clause):</b><br/>हम सत्यनिष्ठा से प्रतिज्ञान करते हैं कि प्रस्तुत किए गए समस्त दस्तावेज एवं विवरण पूर्णतः सत्य हैं।", ParagraphStyle('Hindi', parent=body_style, fontName='Helvetica-Oblique', textColor=colors.HexColor("#222222"))),
            Spacer(1, 20),
            Paragraph("<b>DEPONENT VERIFICATION</b><br/>Verified at New Delhi on this day that the contents of this affidavit are true and correct to my personal knowledge.", body_style),
            Spacer(1, 25),
            Table([
                [Paragraph("<b>Before Me:</b><br/>Advocate & Notary Public<br/>Govt. of India Registered", body_style),
                 Paragraph(f"<b>Deponent Signature:</b><br/>{trustee_name}<br/>Authorized Signatory", body_style)]
            ], colWidths=[250, 250], style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        ]

        doc.build(elements, canvasmaker=NumberedCanvas)
        return buf.getvalue()

    @staticmethod
    def generate_lease_deed_pdf(
        inst_name: str,
        pid: str,
        address: str,
        lease_start: str = "2020-04-01",
        lease_expiry: str = "2050-03-31",
        acres: float = 5.25,
        doc_no: str = "SUBREG-DL-2020-8910",
        corrupt_signature: Optional[str] = None
    ) -> bytes:
        # Register mock issuer record
        seal_payload = register_mock_issuer_record(
            issuer_id=ISSUER_SUB_REGISTRAR,
            doc_no=doc_no,
            fields={
                "pid": pid,
                "institution_name": inst_name,
                "lease_start_date": lease_start,
                "lease_expiry_date": lease_expiry,
                "land_area_acres": acres,
                "address": address
            }
        )
        if corrupt_signature:
            seal_payload = dict(seal_payload)
            seal_payload["signature"] = corrupt_signature

        qr_bytes = create_qr_image_bytes(seal_payload)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=45, rightMargin=45, topMargin=50, bottomMargin=50)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('LeaseTitle', fontName='Helvetica-Bold', fontSize=14, alignment=1, textColor=colors.HexColor("#1A365D"), spaceAfter=10)
        body = ParagraphStyle('LeaseBody', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=8)

        qr_img = RLImage(io.BytesIO(qr_bytes), width=85, height=85)

        elements = [
            Paragraph("DEPARTMENT OF REGISTRATION AND STAMPS • REGISTERED LEASE INDENTURE", title_style),
            Paragraph(f"<b>Registration Book 1 • Volume No: 481 • Doc No:</b> {doc_no}", body),
            Paragraph(f"<b>Permanent Institute ID (PID):</b> {pid}", body),
            Paragraph(f"<b>Institution:</b> {inst_name}", body),
            Paragraph(f"<b>Premises Located At:</b> {address}", body),
            Spacer(1, 5),
            Table([
                [Paragraph("<b>Term Commencement:</b>", body), Paragraph(f"from {lease_start}", body),
                 Paragraph("<b>Term Expiration:</b>", body), Paragraph(f"until {lease_expiry}", body)],
                [Paragraph("<b>Total Land Area:</b>", body), Paragraph(f"{acres} acres (contiguous)", body),
                 Paragraph("<b>Tenancy Tenure:</b>", body), Paragraph("30 Years Irrevocable", body)]
            ], colWidths=[120, 130, 120, 130], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ])),
            Spacer(1, 10),
            Paragraph("<b>SCHEDULE OF DEMISED PREMISES:</b> All that piece and parcel of land demarcated for educational purposes conforming strictly to AICTE Land Norms (APH §Appendix-4.1). Lessor covenants peaceful possession.", body),
            Paragraph("The land is free from any encumbrances, charges, mortgage, or pending litigation in any court of competent civil jurisdiction.", body),
            Spacer(1, 10),
            Table([
                [Paragraph("<b>Official Digital Seal & Registry QR:</b><br/>Scan to authenticate with Sub-Registrar Public Ledger via Ed25519 cryptographic key.", body),
                 qr_img],
                [Paragraph("<b>Sub-Registrar Attestation:</b><br/>Registered at District Land Records Office", body),
                 Paragraph("<b>Seal:</b> Registered & Certified", body)]
            ], colWidths=[380, 120], style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (1,0), (1,0), 'CENTER')
            ]))
        ]

        doc.build(elements, canvasmaker=NumberedCanvas)
        return buf.getvalue()

    @staticmethod
    def generate_state_noc_pdf(
        inst_name: str,
        pid: str,
        noc_no: str = "DTE-NOC-2025-4412",
        issue_date: str = "2025-11-20"
    ) -> bytes:
        seal_payload = register_mock_issuer_record(
            issuer_id=ISSUER_STATE_NOC,
            doc_no=noc_no,
            fields={
                "pid": pid,
                "institution_name": inst_name,
                "state_noc_number": noc_no,
                "state_noc_date": issue_date
            }
        )
        qr_bytes = create_qr_image_bytes(seal_payload)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=45, rightMargin=45, topMargin=50, bottomMargin=50)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('NocTitle', fontName='Helvetica-Bold', fontSize=13, alignment=1, textColor=colors.HexColor("#065F46"), spaceAfter=10)
        body = ParagraphStyle('NocBody', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=8)

        qr_img = RLImage(io.BytesIO(qr_bytes), width=85, height=85)

        elements = [
            Paragraph("GOVERNMENT OF STATE • DIRECTORATE OF TECHNICAL EDUCATION", title_style),
            Paragraph("STATUTORY NO OBJECTION CERTIFICATE (NOC)", ParagraphStyle('Sub', fontName='Helvetica-Bold', fontSize=11, alignment=1, textColor=colors.HexColor("#1F2937"), spaceAfter=12)),
            Paragraph(f"<b>NOC Ref No:</b> {noc_no}", body),
            Paragraph(f"<b>Date of Issue:</b> {issue_date}", body),
            Paragraph(f"<b>Permanent Institute ID (PID):</b> {pid}", body),
            Paragraph(f"<b>Institution:</b> {inst_name}", body),
            Spacer(1, 8),
            Paragraph("This Directorate certifies that the State Government has <b>NO OBJECTION</b> for continuation and extension of technical degree courses conducted by the above institution under AICTE regulatory framework.", body),
            Paragraph("The institution complies with State reservations, fee regulatory committee directives, and university syllabus affiliations.", body),
            Spacer(1, 15),
            Table([
                [Paragraph("<b>State Higher Education Authority QR Seal:</b><br/>Digitally signed with Ed25519 key by Directorate of Technical Education.", body),
                 qr_img],
                [Paragraph("<b>Competent Authority:</b><br/>Director, Technical Education", body),
                 Paragraph("<b>Status:</b> Approved & Clear", body)]
            ], colWidths=[380, 120], style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (1,0), (1,0), 'CENTER')
            ]))
        ]

        doc.build(elements, canvasmaker=NumberedCanvas)
        return buf.getvalue()

    @staticmethod
    def generate_ter_receipt_pdf(
        inst_name: str,
        pid: str,
        txn_id: str = "TER-2026-99120",
        amount: float = 100000.0,
        payment_date: str = "2026-01-10"
    ) -> bytes:
        seal_payload = register_mock_issuer_record(
            issuer_id=ISSUER_TER_PAY,
            doc_no=txn_id,
            fields={
                "pid": pid,
                "institution_name": inst_name,
                "ter_transaction_id": txn_id,
                "ter_amount": amount,
                "ter_payment_date": payment_date
            }
        )
        qr_bytes = create_qr_image_bytes(seal_payload)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=45, rightMargin=45, topMargin=50, bottomMargin=50)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('TerTitle', fontName='Helvetica-Bold', fontSize=13, alignment=1, textColor=colors.HexColor("#1E3A8A"), spaceAfter=10)
        body = ParagraphStyle('TerBody', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=6)

        qr_img = RLImage(io.BytesIO(qr_bytes), width=85, height=85)

        elements = [
            Paragraph("ALL INDIA COUNCIL FOR TECHNICAL EDUCATION • PAYMENT GATEWAY", title_style),
            Paragraph("TECHNICAL EDUCATION REGULATORY (TER) FEE RECEIPT", ParagraphStyle('TerSub', fontName='Helvetica-Bold', fontSize=11, alignment=1, spaceAfter=10)),
            Table([
                [Paragraph("<b>Transaction ID:</b>", body), Paragraph(txn_id, body)],
                [Paragraph("<b>Paid On:</b>", body), Paragraph(payment_date, body)],
                [Paragraph("<b>Permanent Institute ID (PID):</b>", body), Paragraph(pid, body)],
                [Paragraph("<b>Institution:</b>", body), Paragraph(inst_name, body)],
                [Paragraph("<b>Regulatory Fee Amount:</b>", body), Paragraph(f"INR {amount:,.2f}", body)],
                [Paragraph("<b>Payment Status:</b>", body), Paragraph("<font color='#059669'><b>SUCCESS / SETTLED</b></font>", body)],
                [Paragraph("<b>Bank Gateway Ref:</b>", body), Paragraph("SBI-E-PAY-REC-901238472", body)]
            ], colWidths=[180, 320], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ])),
            Spacer(1, 15),
            Table([
                [Paragraph("<b>Treasury Verification QR:</b><br/>Ed25519 signed instant settlement proof.", body), qr_img]
            ], colWidths=[380, 120], style=TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        ]

        doc.build(elements, canvasmaker=NumberedCanvas)
        return buf.getvalue()

    @staticmethod
    def generate_nba_certificate_pdf(
        inst_name: str,
        pid: str,
        acc_no: str = "NBA-ACC-2024-1189",
        valid_upto: str = "2027-06-30"
    ) -> bytes:
        seal_payload = register_mock_issuer_record(
            issuer_id=ISSUER_NBA,
            doc_no=acc_no,
            fields={
                "pid": pid,
                "institution_name": inst_name,
                "nba_accreditation_number": acc_no,
                "nba_valid_upto": valid_upto
            }
        )
        qr_bytes = create_qr_image_bytes(seal_payload)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=45, rightMargin=45, topMargin=50, bottomMargin=50)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('NbaTitle', fontName='Helvetica-Bold', fontSize=14, alignment=1, textColor=colors.HexColor("#7C2D12"), spaceAfter=10)
        body = ParagraphStyle('NbaBody', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=6)

        qr_img = RLImage(io.BytesIO(qr_bytes), width=85, height=85)

        elements = [
            Paragraph("NATIONAL BOARD OF ACCREDITATION • INDIA", title_style),
            Paragraph("CERTIFICATE OF TECHNICAL PROGRAM ACCREDITATION", ParagraphStyle('Sub', fontName='Helvetica-Bold', fontSize=11, alignment=1, spaceAfter=12)),
            Paragraph(f"<b>Certificate No:</b> {acc_no}", body),
            Paragraph(f"<b>Permanent Institute ID (PID):</b> {pid}", body),
            Paragraph(f"<b>Institution:</b> {inst_name}", body),
            Paragraph(f"<b>Accreditation Status:</b> Tier-1 Accredited (Score: 742/1000)", body),
            Paragraph(f"<b>Valid Through:</b> {valid_upto}", body),
            Spacer(1, 10),
            Paragraph("The Competent Authority of NBA has granted accreditation to the Computer Science & Engineering and Electronics Engineering undergraduate programs conforming to Washington Accord International standards.", body),
            Spacer(1, 15),
            Table([
                [Paragraph("<b>NBA Cryptographic Verification Seal:</b><br/>Authenticated against NBA National Accreditation Registry.", body), qr_img]
            ], colWidths=[380, 120], style=TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        ]

        doc.build(elements, canvasmaker=NumberedCanvas)
        return buf.getvalue()

    @staticmethod
    def generate_lab_photo(
        inst_name: str,
        pid: str,
        workstation_count: int = 40
    ) -> bytes:
        """
        Creates a synthetic laboratory photo with workstations, monitors, chairs, and geo-watermark.
        """
        width, height = 800, 600
        img = PILImage.new("RGB", (width, height), color=(240, 243, 246))
        draw = ImageDraw.Draw(img)

        # Draw room perspective grid (lab floor and ceiling)
        draw.rectangle([0, 0, width, 180], fill=(225, 230, 238))  # Ceiling
        draw.rectangle([0, 420, width, height], fill=(190, 195, 205))  # Floor

        # Draw workstation rows
        cols = 5
        rows = 4
        for r in range(rows):
            y_base = 200 + r * 55
            for c in range(cols):
                x_base = 60 + c * 140
                # Desk
                draw.rectangle([x_base, y_base + 20, x_base + 110, y_base + 38], fill=(130, 95, 60), outline=(80, 60, 40))
                # Monitor
                draw.rectangle([x_base + 35, y_base, x_base + 75, y_base + 22], fill=(40, 45, 55), outline=(20, 20, 20))
                # Keyboard
                draw.rectangle([x_base + 25, y_base + 24, x_base + 85, y_base + 32], fill=(70, 75, 80))
                # Chair
                draw.ellipse([x_base + 40, y_base + 36, x_base + 70, y_base + 52], fill=(30, 30, 70))

        # Watermark & Geo-tag banner
        banner_rect = [10, height - 60, width - 10, height - 10]
        draw.rectangle(banner_rect, fill=(15, 23, 42))
        watermark_text = f"LAB GEO-TAG • {inst_name} (PID: {pid}) • LAT: 28.5355° N, LON: 77.3910° E • AICTE APH AUDIT"
        draw.text((25, height - 42), watermark_text, fill=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
