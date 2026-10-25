from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import yaml
from dateutil import parser as date_parser
from rapidfuzz import fuzz
from backend.app.config import RULES_DIR
from backend.app.models import Claim, StatusEnum
from backend.app.lanes.content import get_benign_explanations

TEMPORAL_RULES_PATH = RULES_DIR / "temporal_rules.yaml"

def load_temporal_rules() -> Dict[str, Any]:
    if TEMPORAL_RULES_PATH.exists():
        try:
            with open(TEMPORAL_RULES_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Temporal] Error loading temporal rules: {e}")
    return {}

import re

def parse_iso_date(date_str: str) -> Optional[datetime]:
    try:
        s = str(date_str).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return datetime.fromisoformat(s[:10])
        return date_parser.parse(s, dayfirst=True)
    except Exception:
        return None


class TemporalEngine:
    @classmethod
    def evaluate_graph(
        cls,
        claims: List[Claim],
        application_date_str: str = "2026-03-01"
    ) -> Dict[str, Any]:
        """
        Evaluates temporal and identity consistency across all claims in an application.
        Emits contradiction edges between conflicting claims formatted for Cytoscape.js.
        """
        rules_cfg = load_temporal_rules()
        temp_rules = rules_cfg.get("temporal_rules", [])
        ident_rules = rules_cfg.get("identity_consistency_rules", [])

        app_date = parse_iso_date(application_date_str) or datetime(2026, 3, 1)

        # Index claims by field name
        claims_by_field: Dict[str, List[Claim]] = {}
        nodes = []
        for c in claims:
            claims_by_field.setdefault(c.field, []).append(c)
            nodes.append({
                "data": {
                    "id": c.id,
                    "label": f"{c.field}: {c.value[:22]}",
                    "field": c.field,
                    "value": c.value,
                    "status": c.status,
                    "doc_id": c.doc_id,
                    "page": c.page
                }
            })

        edges = []
        contradictions = []

        # ----------------- 1. Temporal Date Logic Rules -----------------
        # Helper to get first normalized date claim
        def get_date_claim(field_name: str) -> Optional[Tuple[datetime, Claim]]:
            cl_list = claims_by_field.get(field_name, [])
            for c in cl_list:
                dt = parse_iso_date(c.normalized_value or c.value)
                if dt:
                    return (dt, c)
            return None

        lease_start = get_date_claim("lease_start_date")
        affidavit_d = get_date_claim("affidavit_date")
        lease_exp = get_date_claim("lease_expiry_date")
        noc_d = get_date_claim("state_noc_date")
        ter_d = get_date_claim("ter_payment_date")

        # Rule TR_LEASE_BEFORE_AFFIDAVIT: lease_start <= affidavit_date
        if lease_start and affidavit_d:
            if lease_start[0] > affidavit_d[0]:
                rule_id = "TR_LEASE_BEFORE_AFFIDAVIT"
                reason = f"Temporal violation: Lease deed execution ({lease_start[0].strftime('%Y-%m-%d')}) occurs after affidavit declaration ({affidavit_d[0].strftime('%Y-%m-%d')})."
                edge_id = f"edge-{lease_start[1].id}-{affidavit_d[1].id}"
                edges.append({
                    "data": {
                        "id": edge_id,
                        "source": lease_start[1].id,
                        "target": affidavit_d[1].id,
                        "label": rule_id,
                        "reason": reason,
                        "type": "contradiction"
                    }
                })
                contradictions.append({
                    "rule_id": rule_id,
                    "claim_a_id": lease_start[1].id,
                    "claim_b_id": affidavit_d[1].id,
                    "reason": reason,
                    "benign_explanations": get_benign_explanations("DATE_ORDER_VIOLATION")
                })

        # Rule TR_AFFIDAVIT_BEFORE_APP: affidavit_date <= application_date
        if affidavit_d:
            if affidavit_d[0] > app_date + timedelta(days=1):
                rule_id = "TR_AFFIDAVIT_BEFORE_APP"
                reason = f"Temporal violation: Affidavit date ({affidavit_d[0].strftime('%Y-%m-%d')}) is after application filing cutoff ({application_date_str})."
                edges.append({
                    "data": {
                        "id": f"edge-aff-app-{affidavit_d[1].id}",
                        "source": affidavit_d[1].id,
                        "target": affidavit_d[1].id,
                        "label": rule_id,
                        "reason": reason,
                        "type": "contradiction"
                    }
                })
                contradictions.append({
                    "rule_id": rule_id,
                    "claim_a_id": affidavit_d[1].id,
                    "claim_b_id": affidavit_d[1].id,
                    "reason": reason,
                    "benign_explanations": get_benign_explanations("DATE_ORDER_VIOLATION")
                })

        # Rule TR_LEASE_MIN_VALIDITY: lease_expiry >= application_date + 365 days
        if lease_exp:
            required_min_exp = app_date + timedelta(days=365)
            if lease_exp[0] < required_min_exp:
                rule_id = "TR_LEASE_MIN_VALIDITY"
                reason = f"Tenancy deficiency: Lease deed expires on {lease_exp[0].strftime('%Y-%m-%d')}, less than prescribed 12 months minimum remaining tenancy."
                edges.append({
                    "data": {
                        "id": f"edge-lease-exp-{lease_exp[1].id}",
                        "source": lease_exp[1].id,
                        "target": lease_exp[1].id,
                        "label": rule_id,
                        "reason": reason,
                        "type": "contradiction"
                    }
                })
                contradictions.append({
                    "rule_id": rule_id,
                    "claim_a_id": lease_exp[1].id,
                    "claim_b_id": lease_exp[1].id,
                    "reason": reason,
                    "benign_explanations": get_benign_explanations("LEASE_EXPIRY_CRITICAL")
                })

        # Rule TR_TER_PAYMENT_TIMELINESS: ter_payment_date <= application_date
        if ter_d:
            if ter_d[0] > app_date + timedelta(days=2):
                rule_id = "TR_TER_PAYMENT_TIMELINESS"
                reason = f"Fee transaction date ({ter_d[0].strftime('%Y-%m-%d')}) occurs after online submission date ({application_date_str})."
                edges.append({
                    "data": {
                        "id": f"edge-ter-timeliness-{ter_d[1].id}",
                        "source": ter_d[1].id,
                        "target": ter_d[1].id,
                        "label": rule_id,
                        "reason": reason,
                        "type": "contradiction"
                    }
                })
                contradictions.append({
                    "rule_id": rule_id,
                    "claim_a_id": ter_d[1].id,
                    "claim_b_id": ter_d[1].id,
                    "reason": reason,
                    "benign_explanations": get_benign_explanations("TER_PAYMENT_PENDING")
                })

        # ----------------- 2. Cross-Document Identity Concordance -----------------
        # Cross-document PID concordance
        pid_claims = claims_by_field.get("pid", [])
        if len(pid_claims) >= 2:
            base_pid = pid_claims[0].normalized_value or pid_claims[0].value
            for other_pid_claim in pid_claims[1:]:
                oth_val = other_pid_claim.normalized_value or other_pid_claim.value
                if base_pid != oth_val:
                    rule_id = "IR_PID_CROSS_DOC"
                    reason = f"Identity discrepancy: Document PID '{oth_val}' conflicts with '{base_pid}' across uploaded documents."
                    edges.append({
                        "data": {
                            "id": f"edge-pid-{pid_claims[0].id}-{other_pid_claim.id}",
                            "source": pid_claims[0].id,
                            "target": other_pid_claim.id,
                            "label": rule_id,
                            "reason": reason,
                            "type": "contradiction"
                        }
                    })
                    contradictions.append({
                        "rule_id": rule_id,
                        "claim_a_id": pid_claims[0].id,
                        "claim_b_id": other_pid_claim.id,
                        "reason": reason,
                        "benign_explanations": get_benign_explanations("NAME_MISMATCH")
                    })

        # Cross-document Institution Name concordance
        name_claims = claims_by_field.get("institution_name", [])
        if len(name_claims) >= 2:
            base_name = name_claims[0].normalized_value or name_claims[0].value
            for other_name_claim in name_claims[1:]:
                oth_name = other_name_claim.normalized_value or other_name_claim.value
                sim = fuzz.token_sort_ratio(base_name.lower(), oth_name.lower())
                if sim < 85:
                    rule_id = "IR_INST_NAME_MATCH"
                    reason = f"Nomenclature divergence ({sim}% match): '{oth_name}' contradicts '{base_name}'."
                    edges.append({
                        "data": {
                            "id": f"edge-name-{name_claims[0].id}-{other_name_claim.id}",
                            "source": name_claims[0].id,
                            "target": other_name_claim.id,
                            "label": rule_id,
                            "reason": reason,
                            "type": "contradiction"
                        }
                    })
                    contradictions.append({
                        "rule_id": rule_id,
                        "claim_a_id": name_claims[0].id,
                        "claim_b_id": other_name_claim.id,
                        "reason": reason,
                        "benign_explanations": get_benign_explanations("NAME_MISMATCH")
                    })

        # If no contradiction edges found, connect sequential claims with neutral structural edges
        if not edges and len(nodes) > 1:
            for i in range(len(nodes) - 1):
                edges.append({
                    "data": {
                        "id": f"edge-seq-{i}",
                        "source": nodes[i]["data"]["id"],
                        "target": nodes[i + 1]["data"]["id"],
                        "label": "CONCORDANT",
                        "type": "structural"
                    }
                })

        return {
            "elements": {
                "nodes": nodes,
                "edges": edges
            },
            "contradictions": contradictions,
            "total_nodes": len(nodes),
            "total_contradictions": len(contradictions)
        }
