import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import numpy as np
from backend.app.lanes.forensic import ForensicLane
from backend.synth.forge import DocumentTamperer

def test_forensic_lane_signals():
    # 1. Test ELA
    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 200
    dummy_img[50:100, 50:100] = [10, 20, 200]  # Injected high-contrast patch
    score, bbox, reason = ForensicLane.compute_ela(dummy_img)
    assert 0.0 <= score <= 1.0
    assert len(bbox) == 4
    assert "preliminary indicator" in reason.lower()

    # 2. Test Noise residual
    score_n, bbox_n, reason_n = ForensicLane.compute_noise_inconsistency(dummy_img)
    assert 0.0 <= score_n <= 1.0
    assert "preliminary indicator" in reason_n.lower()

    # 3. Test Metadata check with Photoshop / Canva
    fake_meta = {"producer": "Adobe Photoshop 24.1", "creator": "Canva"}
    meta_flags = ForensicLane.analyze_pdf_metadata(fake_meta, b"%PDF-1.4 %%EOF %%EOF %%EOF %%EOF")
    assert len(meta_flags) >= 1
    assert any("photoshop" in f["plain_language_reason"].lower() or "canva" in f["plain_language_reason"].lower() for f in meta_flags)
    assert all("preliminary indicator" in f["plain_language_reason"].lower() for f in meta_flags)

    # 4. Test Mixed font spans
    font_spans = [
        {"font": "Helvetica", "size": 10.0, "bbox": [0.1, 0.1, 0.15, 0.25]},
        {"font": "Times-Bold", "size": 14.0, "bbox": [0.1, 0.20, 0.15, 0.35]}
    ]
    claims = [{"field": "lease_expiry_date", "bbox": [0.09, 0.09, 0.16, 0.36]}]
    font_findings = ForensicLane.analyze_mixed_font_spans(font_spans, claims)
    assert len(font_findings) == 1
    assert "MIXED_FONT_TYPOGRAPHY" in font_findings[0]["reason_code"]
    assert "preliminary indicator" in font_findings[0]["plain_language_reason"].lower()

    print("STAGE 1 FORENSIC LANE TESTS PASSED!")

if __name__ == "__main__":
    test_forensic_lane_signals()
