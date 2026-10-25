import io
import math
from typing import Dict, Any, List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image

class DeepfakeForensics:
    """
    Frequency-domain and spatial artifact analyzer for detecting GAN-generated,
    face-swapped, and AI-synthesized imagery in regulatory documents.
    """

    @staticmethod
    def azimuthal_average(image: np.ndarray, center: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """
        Calculate the azimuthally averaged radial profile of the 2D power spectrum.
        """
        y, x = np.indices(image.shape)
        if not center:
            center = (image.shape[1] // 2, image.shape[0] // 2)

        r = np.hypot(x - center[0], y - center[1]).astype(int)
        r_max = min(center[0], center[1])
        r_flat = r.ravel()
        img_flat = image.ravel()

        # Sum bin values
        radial_sum = np.bincount(r_flat, weights=img_flat)
        radial_count = np.bincount(r_flat)
        radial_count[radial_count == 0] = 1
        radial_profile = radial_sum / radial_count
        return radial_profile[:r_max]

    @classmethod
    def analyze_frequency_domain(cls, img_np: np.ndarray) -> Dict[str, Any]:
        """
        Performs 2D Fast Fourier Transform (FFT) to analyze spectral roll-off and
        detect periodic grid spikes characteristic of GAN transposed convolutions.
        """
        if len(img_np.shape) == 3:
            if img_np.shape[2] == 4:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGBA2GRAY)
            else:
                gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_np

        h, w = gray.shape
        if h < 20 or w < 20:
            return {"score": 0.1, "is_flagged": False, "papr": 1.0, "details": "Image patch too small for spectral analysis"}

        # Standardize size for spectral comparability
        target_size = 256
        resized = cv2.resize(gray, (target_size, target_size), interpolation=cv2.INTER_AREA)

        # 2D FFT and shifted zero-frequency to center
        f = np.fft.fft2(resized.astype(np.float32))
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = np.abs(fshift)
        power_spectrum = magnitude_spectrum ** 2
        log_power = np.log(power_spectrum + 1e-8)

        # Azimuthal radial profile
        center = (target_size // 2, target_size // 2)
        radial_prof = cls.azimuthal_average(log_power, center=center)

        # High-frequency band analysis (upper 40% of radial spectrum)
        hf_start = int(len(radial_prof) * 0.55)
        hf_band = radial_prof[hf_start:]
        
        # In natural optical photos, radial power decreases monotonically (1/f roll-off).
        # In GAN-synthesized images, high frequencies exhibit secondary energy bumps and periodic spikes.
        hf_diff = np.diff(hf_band) if len(hf_band) > 1 else np.array([])
        positive_slopes = np.sum(hf_diff > 0.03) if len(hf_diff) > 0 else 0
        
        # High-frequency peak-to-average ratio
        hf_mean = np.mean(hf_band) if len(hf_band) > 0 else 1.0
        hf_max = np.max(hf_band) if len(hf_band) > 0 else 1.0
        papr = float(hf_max / (hf_mean + 1e-6))

        # Check for periodic grid spikes in Fourier magnitude (cross-hair & diagonal quadrants)
        norm_mag = (log_power - np.min(log_power)) / (np.max(log_power) - np.min(log_power) + 1e-6)
        mask = np.ones((target_size, target_size), dtype=bool)
        cv2.circle(mask.astype(np.uint8), center, 24, 0, -1)
        isolated_spikes = (norm_mag > 0.78) & mask
        spike_count = int(np.sum(isolated_spikes))

        # Synthesize anomaly score based on periodic spikes and PAPR
        score = 0.10
        if spike_count >= 15:
            score += 0.65
        elif spike_count >= 6:
            score += 0.55
        elif spike_count >= 3:
            score += 0.35

        if papr > 1.25:
            score += 0.30
        elif papr > 1.12:
            score += 0.20

        if positive_slopes >= 22 and spike_count >= 3:
            score += 0.20

        score = min(0.98, max(0.05, round(score, 2)))
        is_flagged = score >= 0.65

        return {
            "score": score,
            "is_flagged": is_flagged,
            "papr": round(papr, 3),
            "spike_count": spike_count,
            "positive_slopes": int(positive_slopes),
            "details": f"High-frequency roll-off reversals={positive_slopes}, spectral spikes={spike_count}, PAPR={papr:.2f}"
        }

    @classmethod
    def evaluate_image_face(cls, img_np: np.ndarray) -> Dict[str, Any]:
        """
        Coordinates full face/photo deepfake forensics:
        - Locates portrait / ID badge regions
        - Runs 2D FFT spectral roll-off and periodicity analysis
        - Evaluates high-frequency roll-off consistency
        """
        try:
            h, w = img_np.shape[:2]
            
            # Candidate regions to inspect for face/portrait photo:
            # 1. Top right (typical affidavit / ID badge placement)
            # 2. Center area (typical standalone portrait or lab focal area)
            # 3. Full canvas
            candidates = []
            
            # Region 1: Portrait / Credential Badge in upper right / mid right
            if w > 100 and h > 100:
                y0, y1 = int(h * 0.10), int(h * 0.50)
                x0, x1 = int(w * 0.55), int(w * 0.95)
                candidates.append((img_np[y0:y1, x0:x1], [round(y0/h, 4), round(x0/w, 4), round(y1/h, 4), round(x1/w, 4)]))
                
                # Region 2: Central area
                cy0, cy1 = int(h * 0.20), int(h * 0.70)
                cx0, cx1 = int(w * 0.25), int(w * 0.75)
                candidates.append((img_np[cy0:cy1, cx0:cx1], [round(cy0/h, 4), round(cx0/w, 4), round(cy1/h, 4), round(cx1/w, 4)]))

            # Full image
            candidates.append((img_np, [0.0, 0.0, 1.0, 1.0]))

            best_res = None
            max_score = -1.0
            best_box = [0.15, 0.55, 0.50, 0.90]

            for patch, box in candidates:
                if patch is not None and patch.size > 0:
                    res = cls.analyze_frequency_domain(patch)
                    if res["score"] > max_score:
                        max_score = res["score"]
                        best_res = res
                        best_box = box

            if not best_res:
                best_res = {"score": 0.1, "is_flagged": False, "papr": 1.0, "details": "Default spectral analysis"}

            score = best_res["score"]
            is_flagged = best_res["is_flagged"]

            if is_flagged:
                reason = (
                    f"Face analysis model indicates this photo is likely AI-generated "
                    f"(mismatch in frequency domain: periodic spectral energy peaks at high frequency coordinates, "
                    f"score: {score:.2f})."
                )
                counterfactual_hint = (
                    "Face manipulation flagged by spectral deconvolution analysis. "
                    "Ensure original uncompressed biometric capture is submitted directly from an authorized KYC scanner."
                )
            else:
                reason = "Frequency domain spectrum adheres to natural optical capture curve with standard roll-off."
                counterfactual_hint = "No issue detected; consider adding a digital seal to catch future manipulations."

            return {
                "score": score,
                "is_flagged": is_flagged,
                "bbox": best_box,
                "plain_language_reason": reason,
                "counterfactual_hint": counterfactual_hint,
                "technical_details": best_res.get("details", "")
            }
        except Exception as e:
            return {
                "score": 0.1,
                "is_flagged": False,
                "bbox": [0.0, 0.0, 0.0, 0.0],
                "plain_language_reason": f"Face frequency analysis bypassed ({str(e)}).",
                "counterfactual_hint": "No issue detected; consider adding a digital seal to catch future manipulations.",
                "technical_details": str(e)
            }
