import io
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
import cv2
import numpy as np
import fitz  # PyMuPDF
from PIL import Image
from backend.synth.generate_docs import DocumentGenerator, create_qr_image_bytes

GROUND_TRUTH_FILE = Path(__file__).resolve().parent / "ground_truth.json"

class DocumentTamperer:
    @staticmethod
    def tamper_pdf_metadata(
        pdf_bytes: bytes,
        suspicious_producer: str = "Adobe Photoshop 24.1 (Windows)"
    ) -> bytes:
        """Injects editing software tags into PDF metadata."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        meta = doc.metadata or {}
        meta["producer"] = suspicious_producer
        meta["creator"] = "Canva Design Platform"
        doc.set_metadata(meta)
        return doc.tobytes()

    @staticmethod
    def tamper_qr_signature(
        inst_name: str = "Technical Campus",
        pid: str = "1-1029384753",
        address: str = "Institutional Enclave",
        invalid_signature: str = "AAAA" * 16
    ) -> bytes:
        """Generates document with corrupt Ed25519 signature in embedded QR seal."""
        return DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst_name,
            pid=pid,
            address=address,
            corrupt_signature=invalid_signature
        )

    @staticmethod
    def tamper_text_overlay(
        pdf_bytes: bytes,
        original_text: str = "30 Years Irrevocable",
        forged_text: str = "99 Years Perpetual"
    ) -> bytes:
        """White-out rectangle over text + insertion of different font."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        rects = page.search_for(original_text)
        if rects:
            for r in rects:
                page.draw_rect(r, color=(1, 1, 1), fill=(1, 1, 1))
                page.insert_text((r.x0, r.y1 - 2), forged_text, fontname="Courier-Bold", fontsize=11, color=(0.7, 0, 0))
        return doc.tobytes()

    @staticmethod
    def tamper_expired_lease(
        inst_name: str,
        pid: str,
        address: str
    ) -> bytes:
        """Lease deed with expired tenure."""
        return DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst_name,
            pid=pid,
            address=address,
            lease_start="2010-01-01",
            lease_expiry="2024-12-31",
            acres=4.5,
            doc_no="SUBREG-DL-EXPIRED-1029"
        )

    @staticmethod
    def tamper_insufficient_ter_fee(
        inst_name: str,
        pid: str
    ) -> bytes:
        """TER fee underpaid."""
        return DocumentGenerator.generate_ter_receipt_pdf(
            inst_name=inst_name,
            pid=pid,
            txn_id="TER-2026-SHORT-7718",
            amount=25000.0,
            payment_date="2026-01-05"
        )

    @staticmethod
    def tamper_address_divergence(
        inst_name: str,
        pid: str
    ) -> bytes:
        """Campus address divergent from AICTE master record."""
        return DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst_name,
            pid=pid,
            address="Plot 99, Sector 44, Bengaluru, Karnataka - 560001",
            lease_start="2022-01-01",
            lease_expiry="2052-12-31",
            acres=3.2,
            doc_no="SUBREG-KA-2022-0041"
        )

    @staticmethod
    def tamper_copy_move_image(img_bytes: bytes) -> bytes:
        """Clones a visual patch within the same image to trigger ORB feature matching."""
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_np = np.array(pil_img)
        h, w, _ = img_np.shape

        # Clone a 80x80 patch from (100, 100) to (100, 350)
        patch = img_np[80:160, 80:160].copy()
        img_np[80:160, 320:400] = patch

        out_pil = Image.fromarray(img_np)
        buf = io.BytesIO()
        out_pil.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    @staticmethod
    def tamper_jpeg_recompress(img_bytes: bytes) -> bytes:
        """Dual-pass JPEG recompression to trigger ELA & noise residual disparity."""
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        buf1 = io.BytesIO()
        pil_img.save(buf1, format="JPEG", quality=55)
        buf1.seek(0)
        pil_mid = Image.open(buf1)
        buf2 = io.BytesIO()
        pil_mid.save(buf2, format="JPEG", quality=95)
        return buf2.getvalue()

    @classmethod
    def generate_drill_suite(cls) -> List[Dict[str, Any]]:
        """
        Builds the 10 canonical attack variants with ground-truth labels for evaluation.
        """
        inst_name = "Aryabhata Institute of Engineering & Technology"
        pid = "1-1029384751"
        addr = "Plot 12, Institutional Area, Sector 62, Noida, Uttar Pradesh - 201309"

        # Base clean documents
        clean_aff = DocumentGenerator.generate_affidavit_pdf(inst_name, pid, "Dr. K. S. Radhakrishnan")
        clean_lease = DocumentGenerator.generate_lease_deed_pdf(inst_name, pid, addr)
        clean_noc = DocumentGenerator.generate_state_noc_pdf(inst_name, pid)
        clean_ter = DocumentGenerator.generate_ter_receipt_pdf(inst_name, pid)
        clean_lab = DocumentGenerator.generate_lab_photo(inst_name, pid)

        suite = [
            {
                "attack_id": "ATK-01",
                "attack_type": "wrong_signature",
                "filename": "Lease_Forged_Ed25519_Seal.pdf",
                "doc_type": "lease_deed",
                "bytes": cls.tamper_qr_signature(inst_name, pid, addr),
                "expected_lane": "provenance",
                "expected_reason_code": "SEAL_SIGNATURE_MISMATCH",
                "description": "Ed25519 signature corrupted in QR seal"
            },
            {
                "attack_id": "ATK-02",
                "attack_type": "mismatched_address",
                "filename": "Lease_Divergent_Campus_Address.pdf",
                "doc_type": "lease_deed",
                "bytes": cls.tamper_address_divergence(inst_name, pid),
                "expected_lane": "content",
                "expected_reason_code": "ADDRESS_MISMATCH",
                "description": "Campus address in lease deed diverges from AICTE master"
            },
            {
                "attack_id": "ATK-03",
                "attack_type": "amount_edit",
                "filename": "TER_Receipt_Underpaid.pdf",
                "doc_type": "ter_receipt",
                "bytes": cls.tamper_insufficient_ter_fee(inst_name, pid),
                "expected_lane": "content",
                "expected_reason_code": "TER_AMOUNT_INSUFFICIENT",
                "description": "Regulatory fee paid (INR 25,000) below mandatory tier"
            },
            {
                "attack_id": "ATK-04",
                "attack_type": "expired_doc",
                "filename": "Lease_Deed_Expired.pdf",
                "doc_type": "lease_deed",
                "bytes": cls.tamper_expired_lease(inst_name, pid, addr),
                "expected_lane": "content",
                "expected_reason_code": "EXPIRED_DOCUMENT",
                "description": "Lease tenancy expired prior to approval window"
            },
            {
                "attack_id": "ATK-05",
                "attack_type": "metadata_spoof",
                "filename": "Affidavit_Photoshop_Metadata.pdf",
                "doc_type": "affidavit",
                "bytes": cls.tamper_pdf_metadata(clean_aff),
                "expected_lane": "forensic",
                "expected_reason_code": "SUSPICIOUS_PDF_PRODUCER",
                "description": "PDF producer metadata references Adobe Photoshop"
            },
            {
                "attack_id": "ATK-06",
                "attack_type": "text_pasteover",
                "filename": "Lease_Whiteout_Pasteover.pdf",
                "doc_type": "lease_deed",
                "bytes": cls.tamper_text_overlay(clean_lease),
                "expected_lane": "forensic",
                "expected_reason_code": "MIXED_FONT_TYPOGRAPHY",
                "description": "White-out box with Courier typography spliced over text"
            },
            {
                "attack_id": "ATK-07",
                "attack_type": "copy_move",
                "filename": "Lab_Cloned_Workstation_ORB.jpg",
                "doc_type": "lab_photo",
                "bytes": cls.tamper_copy_move_image(clean_lab),
                "expected_lane": "forensic",
                "expected_reason_code": "COPY_MOVE_CLONE_DETECTED",
                "description": "Duplicated workstation row cloned inside lab photo"
            },
            {
                "attack_id": "ATK-08",
                "attack_type": "jpeg_recompress",
                "filename": "Lab_Double_Compressed.jpg",
                "doc_type": "lab_photo",
                "bytes": cls.tamper_jpeg_recompress(clean_lab),
                "expected_lane": "forensic",
                "expected_reason_code": "ELA_ANOMALY_DETECTED",
                "description": "Dual-pass JPEG recompression introducing ELA residual disparity"
            },
            {
                "attack_id": "ATK-09",
                "attack_type": "date_edit",
                "filename": "Lease_Post_Dated.pdf",
                "doc_type": "lease_deed",
                "bytes": DocumentGenerator.generate_lease_deed_pdf(
                    inst_name, pid, addr,
                    lease_start="2026-05-01",  # After affidavit
                    lease_expiry="2056-04-30"
                ),
                "expected_lane": "temporal",
                "expected_reason_code": "TR_LEASE_BEFORE_AFFIDAVIT",
                "description": "Lease commencement date post-dates affidavit declaration"
            },
            {
                "attack_id": "ATK-10",
                "attack_type": "reuse_duplicate",
                "filename": "Lease_Reused_Acreage.pdf",
                "doc_type": "lease_deed",
                "bytes": clean_lease,  # Exact replica reused
                "expected_lane": "reuse_ring",
                "expected_reason_code": "REUSE_RING_DOCUMENT_COLLISION",
                "description": "Identical lease document and registration number reused across colleges"
            }
        ]

        # Write ground truth JSON
        gt_export = [
            {
                "attack_id": item["attack_id"],
                "attack_type": item["attack_type"],
                "expected_lane": item["expected_lane"],
                "expected_reason_code": item["expected_reason_code"],
                "description": item["description"]
            }
            for item in suite
        ]
        GROUND_TRUTH_FILE.write_text(json.dumps(gt_export, indent=2), encoding="utf-8")
        return suite
