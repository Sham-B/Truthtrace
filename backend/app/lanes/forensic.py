import io
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance
import imagehash
from backend.app.models import LaneVoteEnum, StatusEnum
from backend.app.lanes.content import get_benign_explanations
from backend.app.config import settings

SUSPICIOUS_METADATA_CREATORS = [
    "photoshop", "canva", "gimp", "illustrator", "coreldraw",
    "sejda", "ilovepdf", "smallpdf", "pdfescape", "inkscape"
]

class ForensicLane:
    @staticmethod
    def compute_ela(
        img_np: np.ndarray,
        quality: int = 90
    ) -> Tuple[float, List[float], str]:
        """
        Error Level Analysis (ELA): detects digital image manipulation by analyzing
        compression error discrepancies across the image canvas.
        Returns: (score, normalized_bbox, reason)
        """
        try:
            pil_orig = Image.fromarray(cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB))
            buf = io.BytesIO()
            pil_orig.save(buf, format="JPEG", quality=quality)
            buf.seek(0)
            pil_recompressed = Image.open(buf)

            # Compute difference
            diff = ImageChops.difference(pil_orig, pil_recompressed)
            extrema = diff.getextrema()
            max_diff = max([ex[1] for ex in extrema]) if extrema else 0
            scale = 255.0 / max(1, max_diff)
            diff_enhanced = ImageEnhance.Brightness(diff).enhance(scale)

            # Convert to numpy grayscale
            diff_np = np.array(diff_enhanced.convert("L"))
            h, w = diff_np.shape

            # Find regions with highest residual energy
            thresh = np.percentile(diff_np, 98)
            hot_mask = (diff_np >= thresh).astype(np.uint8) * 255

            contours, _ = cv2.findContours(hot_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, bw, bh = cv2.boundingRect(largest)
                if bw > 15 and bh > 10:
                    score = min(0.95, round(float(np.mean(diff_np[y:y+bh, x:x+bw])) / 180.0, 2))
                    norm_bbox = [
                        round(y / h, 4), round(x / w, 4),
                        round((y + bh) / h, 4), round((x + bw) / w, 4)
                    ]
                    return score, norm_bbox, f"Preliminary indicator: High ELA recompression residual localized around region [{norm_bbox[0]:.2f}, {norm_bbox[1]:.2f}]."

            return 0.1, [0.0, 0.0, 0.0, 0.0], "Preliminary indicator: Uniform ELA compression profile across page."
        except Exception as e:
            return 0.0, [0.0, 0.0, 0.0, 0.0], f"Preliminary indicator: ELA calculation skipped ({e})."

    @staticmethod
    def compute_noise_inconsistency(
        img_np: np.ndarray
    ) -> Tuple[float, List[float], str]:
        """
        Local noise-residual inconsistency: analyzes high-frequency noise variance across
        grid blocks to identify spliced or copy-pasted content.
        """
        try:
            gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
            # High-pass filter via Laplacian
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            h, w = gray.shape

            # Divide into 16x16 grid
            grid_y = 16
            grid_x = 16
            step_y = h // grid_y
            step_x = w // grid_x

            variances = []
            block_coords = []
            for i in range(grid_y):
                for j in range(grid_x):
                    block = laplacian[i*step_y:(i+1)*step_y, j*step_x:(j+1)*step_x]
                    var = float(np.var(block))
                    variances.append(var)
                    block_coords.append((i, j))

            var_arr = np.array(variances)
            mean_var = float(np.mean(var_arr))
            std_var = float(np.std(var_arr))

            content_vars = [v for v in variances if v > 15.0]
            if len(content_vars) >= 6:
                c_mean = float(np.mean(content_vars))
                c_std = float(np.std(content_vars))
                if c_mean > 0:
                    cv_score = c_std / c_mean
                    if cv_score > 3.2:  # Significant localized noise anomaly in content regions
                        max_idx = int(np.argmax(var_arr))
                        mi, mj = block_coords[max_idx]
                        norm_bbox = [
                            round((mi * step_y) / h, 4), round((mj * step_x) / w, 4),
                            round(((mi + 1) * step_y) / h, 4), round(((mj + 1) * step_x) / w, 4)
                        ]
                        score = min(0.9, round(cv_score / 4.0, 2))
                        return score, norm_bbox, f"Preliminary indicator: Noise residual inconsistency detected (CV={cv_score:.2f})."

            return 0.15, [0.0, 0.0, 0.0, 0.0], "Preliminary indicator: Uniform background sensor noise."
        except Exception as e:
            return 0.0, [0.0, 0.0, 0.0, 0.0], f"Preliminary indicator: Noise analysis error ({e})."

    @staticmethod
    def detect_copy_move_orb(
        img_np: np.ndarray
    ) -> Tuple[float, List[float], str]:
        """
        Copy-move forgery detection using ORB descriptor matching.
        Identifies duplicated visual patches within the same document canvas.
        """
        try:
            gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            orb = cv2.ORB_create(nfeatures=1200)
            keypoints, descriptors = orb.detectAndCompute(gray, None)

            if descriptors is None or len(descriptors) < 20:
                return 0.0, [0.0, 0.0, 0.0, 0.0], "Preliminary indicator: Insufficient visual texture for ORB feature matching."

            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
            matches = bf.knnMatch(descriptors, descriptors, k=3)

            duplicate_pairs = []
            for m in matches:
                if len(m) >= 2:
                    # m[0] is self-match (distance=0). Check m[1]
                    d1 = m[1].distance
                    idx_self = m[0].queryIdx
                    idx_other = m[1].trainIdx
                    if idx_self != idx_other and d1 < 12:
                        pt1 = keypoints[idx_self].pt
                        pt2 = keypoints[idx_other].pt
                        dist_spatial = np.hypot(pt1[0] - pt2[0], pt1[1] - pt2[1])
                        # Filter out neighboring points; keep distinct duplicate regions
                        if dist_spatial > 60:
                            duplicate_pairs.append((pt1, pt2))

            if len(duplicate_pairs) >= 300:
                # Duplication cluster detected
                pts_src = [p[0] for p in duplicate_pairs]
                min_x = min(p[0] for p in pts_src)
                max_x = max(p[0] for p in pts_src)
                min_y = min(p[1] for p in pts_src)
                max_y = max(p[1] for p in pts_src)

                norm_bbox = [
                    round(max(0.0, min_y / h), 4), round(max(0.0, min_x / w), 4),
                    round(min(1.0, max_y / h), 4), round(min(1.0, max_x / w), 4)
                ]
                score = min(0.92, round(0.5 + (len(duplicate_pairs) / 500.0), 2))
                return score, norm_bbox, f"Preliminary indicator: Possible copy-move duplication cluster ({len(duplicate_pairs)} feature pairs matched)."

            return 0.1, [0.0, 0.0, 0.0, 0.0], "Preliminary indicator: No cloned texture clusters detected via ORB."
        except Exception as e:
            return 0.0, [0.0, 0.0, 0.0, 0.0], f"Preliminary indicator: Copy-move analysis error ({e})."

    @staticmethod
    def analyze_pdf_metadata(
        metadata: Dict[str, Any],
        doc_bytes: bytes
    ) -> List[Dict[str, Any]]:
        """
        Inspects PDF metadata and binary stream for editing tools, timeline inconsistencies,
        and incremental update blocks.
        """
        anomalies = []
        producer = str(metadata.get("producer", "")).lower()
        creator = str(metadata.get("creator", "")).lower()

        # 1. Suspicious software editor detection
        for s in SUSPICIOUS_METADATA_CREATORS:
            if s in producer or s in creator:
                anomalies.append({
                    "reason_code": "SUSPICIOUS_PDF_PRODUCER",
                    "score": 0.85,
                    "plain_language_reason": f"Preliminary indicator: Document metadata references image editing software ('{producer or creator}') rather than institutional scanner or word processor.",
                    "evidence_field": "pdf_metadata.producer",
                    "rule_id": "FOR_META_PRODUCER"
                })
                break

        # 2. Incremental update count (multiple %%EOF markers)
        eof_count = doc_bytes.count(b"%%EOF")
        if eof_count > 3:
            anomalies.append({
                "reason_code": "PDF_INCREMENTAL_UPDATES",
                "score": 0.65,
                "plain_language_reason": f"Preliminary indicator: PDF structure contains {eof_count} incremental update revisions, indicative of repeated manual modifications.",
                "evidence_field": "pdf_structure.eof_count",
                "rule_id": "FOR_META_UPDATES"
            })

        return anomalies

    @staticmethod
    def analyze_mixed_font_spans(
        font_spans: List[Dict[str, Any]],
        claims: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Inspects PyMuPDF font spans for mixed typography within a single regulatory field.
        """
        findings = []
        for claim in claims:
            c_bbox = claim.get("bbox", [0.0, 0.0, 0.0, 0.0])
            ymin, xmin, ymax, xmax = c_bbox
            field_name = claim.get("field", "")

            # Find all font spans that intersect with this claim bbox
            matched_spans = []
            for s in font_spans:
                s_bbox = s.get("bbox", [0.0, 0.0, 0.0, 0.0])
                sy0, sx0, sy1, sx1 = s_bbox
                # Check bounding box overlap
                if not (sx1 < xmin or sx0 > xmax or sy1 < ymin or sy0 > ymax):
                    matched_spans.append(s)

            if len(matched_spans) >= 2:
                def get_family(f_name: str) -> str:
                    f = (f_name or "").lower().split("-")[0].replace("bold", "").replace("italic", "").replace("oblique", "").strip()
                    return f

                families = set(get_family(s.get("font")) for s in matched_spans if s.get("font"))
                # Filter out dingbats
                families.discard("zapfdingbats")
                sizes = [s.get("size", 0.0) for s in matched_spans if s.get("size")]
                size_delta = (max(sizes) - min(sizes)) if sizes else 0.0

                # Splicing requires different font families (e.g. Times/Courier in Helvetica) or massive size jump (>7pt)
                if len(families) > 1 or size_delta > 7.0:
                    findings.append({
                        "reason_code": "MIXED_FONT_TYPOGRAPHY",
                        "score": 0.78,
                        "field": field_name,
                        "bbox": c_bbox,
                        "plain_language_reason": f"Preliminary indicator: Inconsistent typography spliced inside field '{field_name}' (fonts: {list(families)}, size delta: {size_delta:.1f}pt).",
                        "rule_id": "FOR_TYPO_SPLICE"
                    })

        return findings

    @classmethod
    def evaluate_document(
        cls,
        doc_id: str,
        inspect_data: Dict[str, Any],
        doc_bytes: bytes,
        extracted_claims: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Coordinates full forensic pipeline for a document:
        - ELA, Noise residual, ORB copy-move, Metadata inspection, Font span typography.
        Returns: {
            "vote": LaneVoteEnum,
            "suspicion_score": float,
            "flags": List[Dict[str, Any]]
        }
        """
        pages = inspect_data.get("pages", [])
        flags: List[Dict[str, Any]] = []
        max_score = 0.0

        # 1. Metadata check
        metadata = inspect_data.get("metadata", {})
        meta_anomalies = cls.analyze_pdf_metadata(metadata, doc_bytes)
        for ma in meta_anomalies:
            max_score = max(max_score, ma["score"])
            flags.append({
                "reason_code": ma["reason_code"],
                "plain_language_reason": ma["plain_language_reason"],
                "evidence": {"doc_id": doc_id, "page": 0, "bbox": [0.0, 0.0, 0.05, 0.3]},
                "rule_id": ma["rule_id"],
                "source_lane": "forensic",
                "benign_explanations": get_benign_explanations("FORENSIC_NOISE_ANOMALY")
            })

        # 2. Pixel & Typography Checks across pages
        for p in pages:
            p_num = p.get("page_num", 0)
            render_path = p.get("render_path")
            font_spans = p.get("font_spans", [])

            # Check font spans against claims on this page
            page_claims = [c for c in extracted_claims if c.get("page", 0) == p_num]
            font_findings = cls.analyze_mixed_font_spans(font_spans, page_claims)
            for ff in font_findings:
                max_score = max(max_score, ff["score"])
                flags.append({
                    "reason_code": ff["reason_code"],
                    "plain_language_reason": ff["plain_language_reason"],
                    "evidence": {"doc_id": doc_id, "page": p_num, "bbox": ff["bbox"]},
                    "rule_id": ff["rule_id"],
                    "source_lane": "forensic",
                    "benign_explanations": get_benign_explanations("FORENSIC_NOISE_ANOMALY")
                })

            if render_path and Path(render_path).exists():
                img_cv = cv2.imread(render_path)
                if img_cv is not None:
                    if settings.LOW_MEMORY:
                        h_cv, w_cv = img_cv.shape[:2]
                        if max(h_cv, w_cv) > 1600:
                            scale = 1600.0 / max(h_cv, w_cv)
                            img_cv = cv2.resize(img_cv, (int(w_cv * scale), int(h_cv * scale)), interpolation=cv2.INTER_AREA)

                    # ELA
                    ela_score, ela_box, ela_reason = cls.compute_ela(img_cv)
                    if ela_score > 0.65:
                        max_score = max(max_score, ela_score)
                        flags.append({
                            "reason_code": "ELA_ANOMALY_DETECTED",
                            "plain_language_reason": ela_reason,
                            "evidence": {"doc_id": doc_id, "page": p_num, "bbox": ela_box},
                            "rule_id": "FOR_PIXEL_ELA",
                            "source_lane": "forensic",
                            "benign_explanations": get_benign_explanations("FORENSIC_NOISE_ANOMALY")
                        })

                    # Noise residual inconsistency
                    noise_score, noise_box, noise_reason = cls.compute_noise_inconsistency(img_cv)
                    if noise_score > 0.65:
                        max_score = max(max_score, noise_score)
                        flags.append({
                            "reason_code": "NOISE_RESIDUAL_INCONSISTENCY",
                            "plain_language_reason": noise_reason,
                            "evidence": {"doc_id": doc_id, "page": p_num, "bbox": noise_box},
                            "rule_id": "FOR_PIXEL_NOISE",
                            "source_lane": "forensic",
                            "benign_explanations": get_benign_explanations("FORENSIC_NOISE_ANOMALY")
                        })

                    # ORB copy-move
                    cm_score, cm_box, cm_reason = cls.detect_copy_move_orb(img_cv)
                    if cm_score > 0.65:
                        max_score = max(max_score, cm_score)
                        flags.append({
                            "reason_code": "COPY_MOVE_CLONE_DETECTED",
                            "plain_language_reason": cm_reason,
                            "evidence": {"doc_id": doc_id, "page": p_num, "bbox": cm_box},
                            "rule_id": "FOR_PIXEL_COPY_MOVE",
                            "source_lane": "forensic",
                            "benign_explanations": get_benign_explanations("FORENSIC_NOISE_ANOMALY")
                        })

                    # Deepfake & Face frequency domain analysis
                    try:
                        from backend.app.adversarial.deepfake_detector import DeepfakeForensics
                        df_res = DeepfakeForensics.evaluate_image_face(img_cv)
                        if df_res["is_flagged"]:
                            max_score = max(max_score, df_res["score"])
                            flags.append({
                                "reason_code": "DEEPFAKE_GAN_SYNTHESIS_DETECTED",
                                "plain_language_reason": df_res["plain_language_reason"],
                                "evidence": {"doc_id": doc_id, "page": p_num, "bbox": df_res["bbox"]},
                                "rule_id": "FOR_FACE_DEEPFAKE",
                                "source_lane": "forensic",
                                "benign_explanations": [{
                                    "title": "Camera Sensor Spectral Noise",
                                    "description": "Certain consumer webcams generate subtle periodic pixel noise.",
                                    "settling_evidence": "Physically verify original paper photo with notary embossing."
                                }]
                            })
                    except Exception:
                        pass

        # Determine Forensic Lane Vote
        if max_score >= 0.70:
            vote = LaneVoteEnum.CONTRADICT
        elif max_score >= 0.40:
            vote = LaneVoteEnum.WEAK
        elif len(pages) > 0:
            vote = LaneVoteEnum.SUPPORT
        else:
            vote = LaneVoteEnum.NA

        return {
            "vote": vote,
            "suspicion_score": round(max_score, 2),
            "flags": flags
        }
