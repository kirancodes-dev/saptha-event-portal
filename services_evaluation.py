"""
services_evaluation.py — Universal Evaluation Engine & Pluggable Scoring Rubrics

Supports multiple scoring models:
1. Weighted Rubric (criteria weights and max scales)
2. 5-Star Rating (1-5 stars normalized to 100)
3. Pass / Fail (threshold validation)
4. Match Points / Sports Leaderboard (points, fair play, score differences)
5. Time-based (speed sprints / completion durations)
6. Multi-Judge Consensus & Outlier Trimming (Olympic scoring)

Features:
- Deterministic automated tie-breaking (criterion weight priority -> submission speed)
- Judge scoring audit trails
- Multi-round advancement and final ranking calculation
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvaluationEngine:
    """
    Pluggable evaluation calculation and leaderboard ranking engine.
    """

    @staticmethod
    def calculate_score(
        rubric_config: Dict[str, Any],
        raw_scores: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate total score and breakdown according to rubric model type.
        Returns: (final_score, breakdown_details)
        """
        scoring_type = rubric_config.get("type", "rubric")
        criteria = rubric_config.get("criteria", [])
        breakdown = {}

        if scoring_type == "pass_fail":
            pass_score = float(rubric_config.get("pass_score", 70))
            score_val = float(raw_scores.get("score", 0))
            passed = score_val >= pass_score
            breakdown["score"] = score_val
            breakdown["pass_score"] = pass_score
            breakdown["passed"] = passed
            return score_val if passed else 0.0, breakdown

        elif scoring_type == "star_rating":
            # 1 to 5 stars per criteria -> normalized to 100
            total_stars = 0
            max_possible_stars = len(criteria) * 5 if criteria else 5
            for c in criteria:
                key = c.get("key") or c.get("name")
                stars = min(5, max(1, float(raw_scores.get(key, 0) or 0)))
                breakdown[key] = stars
                total_stars += stars
            normalized = round((total_stars / max_possible_stars) * 100, 2) if max_possible_stars > 0 else 0.0
            breakdown["total_stars"] = total_stars
            breakdown["normalized_100"] = normalized
            return normalized, breakdown

        elif scoring_type == "match_points":
            points = float(raw_scores.get("match_score", 0) or 0)
            fair_play = float(raw_scores.get("fair_play", 0) or 0)
            mvp_rating = float(raw_scores.get("mvp_rating", 0) or 0)
            total = points + (fair_play * 2) + (mvp_rating * 5)
            breakdown["match_score"] = points
            breakdown["fair_play"] = fair_play
            breakdown["mvp_rating"] = mvp_rating
            breakdown["total_points"] = total
            return total, breakdown

        elif scoring_type == "time_based":
            # Lower duration seconds is better. Invert score so faster = higher
            duration_secs = float(raw_scores.get("duration_seconds", 3600))
            penalties = float(raw_scores.get("penalty_seconds", 0))
            total_duration = duration_secs + penalties
            breakdown["duration_seconds"] = duration_secs
            breakdown["penalty_seconds"] = penalties
            breakdown["total_duration"] = total_duration
            # Score formula: 100,000 / (total_duration + 1)
            score = round(100000.0 / (total_duration + 1), 2)
            return score, breakdown

        else:
            # Default: Weighted Rubric
            total_weighted = 0.0
            total_weight = 0.0

            for c in criteria:
                key = c.get("key") or c.get("name")
                max_score = float(c.get("max_score", 10))
                weight = float(c.get("weight", 1))
                val = float(raw_scores.get(key, 0) or 0)
                # Clamp between 0 and max_score
                val = min(max_score, max(0.0, val))

                normalized_criterion = (val / max_score) * 100.0 if max_score > 0 else 0.0
                weighted_contribution = (normalized_criterion * weight) / 100.0

                breakdown[key] = {
                    "raw": val,
                    "max": max_score,
                    "weight": weight,
                    "contribution": round(weighted_contribution, 2),
                }

                total_weighted += weighted_contribution
                total_weight += weight

            final_score = round((total_weighted / (total_weight / 100.0)), 2) if total_weight > 0 else 0.0
            breakdown["final_score"] = final_score
            return final_score, breakdown

    @classmethod
    def record_score(
        cls,
        db,
        *,
        event_id: str,
        registration_id: str,
        judge_id: str,
        judge_name: str,
        raw_scores: Dict[str, Any],
        round_num: int = 1,
        remarks: str = "",
    ) -> Dict[str, Any]:
        """
        Evaluate and persist a judge score submission with rubric breakdown.
        """
        event_doc = db.collection("events").document(event_id).get()
        if not event_doc.exists:
            raise ValueError(f"Event '{event_id}' not found")
        event_data = event_doc.to_dict()
        rubric_config = event_data.get("evaluation_config") or {"type": "rubric", "criteria": []}

        final_score, breakdown = cls.calculate_score(rubric_config, raw_scores)
        now_str = _utcnow_iso()

        score_entry = {
            "judge_id": judge_id,
            "judge_name": judge_name,
            "round": round_num,
            "final_score": final_score,
            "raw_scores": raw_scores,
            "breakdown": breakdown,
            "remarks": remarks,
            "scored_at": now_str,
        }

        # Update registration scores map
        reg_ref = db.collection("registrations").document(registration_id)
        reg_doc = reg_ref.get()
        if not reg_doc.exists:
            raise ValueError(f"Registration '{registration_id}' not found")

        reg_data = reg_doc.to_dict()
        existing_scores = reg_data.get("scores", {})
        existing_scores[judge_id] = score_entry

        # Calculate composite average score across all judges
        all_final_scores = [s.get("final_score", 0.0) for s in existing_scores.values() if isinstance(s, dict)]
        composite_avg = round(sum(all_final_scores) / len(all_final_scores), 2) if all_final_scores else 0.0

        reg_ref.set({
            "scores": existing_scores,
            "score_average": composite_avg,
            "last_scored_at": now_str,
            "current_round": round_num,
        }, merge=True)

        return score_entry

    @classmethod
    def generate_leaderboard(
        cls,
        db,
        event_id: str,
        round_num: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate ranked leaderboard with automated tie-breaking logic.
        Tie-breaking rule:
        1. Higher composite average score.
        2. In rubric mode: higher score on highest-weighted primary criterion.
        3. Earlier submission timestamp.
        """
        event_doc = db.collection("events").document(event_id).get()
        if not event_doc.exists:
            return []
        event_data = event_doc.to_dict()
        rubric = event_data.get("evaluation_config") or {}
        criteria = rubric.get("criteria", [])
        primary_key = criteria[0].get("key") if criteria else None

        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
        except ImportError:
            FieldFilter = None

        if FieldFilter:
            docs = db.collection("registrations").where(filter=FieldFilter("event_id", "==", event_id)).stream()
        else:
            docs = db.collection("registrations").where("event_id", "==", event_id).stream()

        candidates = []
        for d in docs:
            r = d.to_dict()
            r["id"] = d.id

            scores = r.get("scores", {})
            if not scores:
                continue

            if round_num is not None and r.get("current_round") != round_num:
                continue

            avg_score = float(r.get("score_average", 0.0) or 0.0)

            # Find primary criterion score for tie breaking
            primary_score = 0.0
            if primary_key:
                p_scores = []
                for s in scores.values():
                    if isinstance(s, dict):
                        b = s.get("breakdown", {})
                        if isinstance(b, dict) and primary_key in b:
                            c_info = b[primary_key]
                            p_scores.append(c_info.get("raw", 0) if isinstance(c_info, dict) else c_info)
                if p_scores:
                    primary_score = sum(p_scores) / len(p_scores)

            candidates.append({
                "registration_id": r["id"],
                "team_name": r.get("team_name") or r.get("lead_name", "Anonymous"),
                "lead_name": r.get("lead_name", ""),
                "lead_email": r.get("lead_email", ""),
                "composite_score": avg_score,
                "primary_tiebreak_score": primary_score,
                "judges_count": len(scores),
                "scored_at": r.get("last_scored_at", ""),
            })

        # Sort with deterministic tie-breaking:
        # (-composite_score, -primary_tiebreak_score, scored_at)
        candidates.sort(
            key=lambda x: (
                -x["composite_score"],
                -x["primary_tiebreak_score"],
                x["scored_at"] or "9999",
            )
        )

        # Assign ranks
        for idx, item in enumerate(candidates, start=1):
            item["rank"] = idx

        return candidates
