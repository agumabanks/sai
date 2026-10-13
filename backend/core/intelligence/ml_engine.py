"""
Sanaa AI — ML Self-Learning Engine for Skills

Provides:
  - Performance metric aggregation from skill_runs
  - Trend detection (improving/degrading/stable)
  - Anomaly detection on latency/error patterns
  - Parameter optimization from successful runs
  - Composite performance scoring (0-1)
  - Feedback-weighted learning signals
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import Counter, defaultdict

from sqlalchemy import select, desc, func, and_, text
from core.database import (
    AsyncSessionLocal,
    SkillRun,
    SkillMetrics,
    SkillFeedback,
    SkillLearningLog,
    SkillParameterProfile,
    utcnow,
)

logger = logging.getLogger(__name__)


class SkillMLEngine:
    """Core ML engine for skill self-learning and performance optimization."""

    # Weights for composite performance score
    WEIGHT_SUCCESS_RATE = 0.35
    WEIGHT_LATENCY = 0.20
    WEIGHT_USER_RATING = 0.25
    WEIGHT_TREND = 0.10
    WEIGHT_RELIABILITY = 0.10

    # Anomaly thresholds
    LATENCY_ANOMALY_FACTOR = 2.5  # >2.5x avg = anomaly
    ERROR_SPIKE_THRESHOLD = 0.3   # >30% error rate in period = spike

    async def aggregate_metrics(self, period: str = "daily") -> list[dict]:
        """Aggregate skill_runs into SkillMetrics rows for the current period."""
        now = utcnow()

        if period == "hourly":
            period_start = now.replace(minute=0, second=0, microsecond=0)
            lookback = timedelta(hours=1)
        elif period == "daily":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            lookback = timedelta(days=1)
        elif period == "weekly":
            period_start = now - timedelta(days=now.weekday())
            period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
            lookback = timedelta(weeks=1)
        else:
            raise ValueError(f"Unknown period: {period}")

        cutoff = period_start

        async with AsyncSessionLocal() as session:
            from sqlalchemy import case as sa_case, literal_column

            # Get all skill runs in this period
            result = await session.execute(
                select(
                    SkillRun.skill_name,
                    func.count(SkillRun.id).label("total"),
                    func.sum(sa_case((SkillRun.status == "success", 1), else_=0)).label("successes"),
                    func.sum(sa_case((SkillRun.status == "failed", 1), else_=0)).label("failures"),
                    func.sum(sa_case((SkillRun.status == "timeout", 1), else_=0)).label("timeouts"),
                    func.avg(SkillRun.duration_ms).label("avg_ms"),
                )
                .where(SkillRun.started_at >= cutoff)
                .group_by(SkillRun.skill_name)
            )
            rows = result.all()

        aggregated = []
        for row in rows:
            skill_name = row[0]
            total = row[1] or 0
            successes = row[2] or 0
            failures = row[3] or 0
            timeouts = row[4] or 0
            avg_ms = float(row[5] or 0)
            p95_ms = avg_ms * 1.5  # Approximate p95

            if total == 0:
                continue

            success_rate = successes / total if total > 0 else 0

            # Get average user rating for this skill in this period
            avg_rating, rating_count = await self._get_period_rating(skill_name, cutoff)

            # Classify errors
            error_cats = await self._classify_errors(skill_name, cutoff)

            # Calculate trend by comparing to previous period
            trend = await self._calculate_trend(skill_name, period, success_rate, avg_ms)

            # Calculate composite performance score
            perf_score = self._calculate_performance_score(
                success_rate=success_rate,
                avg_ms=avg_ms,
                avg_rating=avg_rating,
                trend=trend,
                total_runs=total,
            )

            # Upsert metrics
            async with AsyncSessionLocal() as session:
                existing = await session.execute(
                    select(SkillMetrics).where(
                        SkillMetrics.skill_name == skill_name,
                        SkillMetrics.period == period,
                        SkillMetrics.period_start == period_start,
                    )
                )
                metrics = existing.scalars().first()

                if metrics:
                    metrics.total_runs = total
                    metrics.success_count = successes
                    metrics.failure_count = failures
                    metrics.timeout_count = timeouts
                    metrics.avg_duration_ms = avg_ms
                    metrics.p95_duration_ms = p95_ms
                    metrics.success_rate = success_rate
                    metrics.avg_user_rating = avg_rating
                    metrics.rating_count = rating_count
                    metrics.error_categories = error_cats
                    metrics.performance_score = perf_score
                    metrics.trend = trend
                else:
                    metrics = SkillMetrics(
                        skill_name=skill_name,
                        period=period,
                        period_start=period_start,
                        total_runs=total,
                        success_count=successes,
                        failure_count=failures,
                        timeout_count=timeouts,
                        avg_duration_ms=avg_ms,
                        p95_duration_ms=p95_ms,
                        success_rate=success_rate,
                        avg_user_rating=avg_rating,
                        rating_count=rating_count,
                        error_categories=error_cats,
                        performance_score=perf_score,
                        trend=trend,
                    )
                    session.add(metrics)

                await session.commit()

            # Detect anomalies
            await self._detect_anomalies(skill_name, avg_ms, success_rate, period)

            aggregated.append({
                "skill_name": skill_name,
                "total_runs": total,
                "success_rate": round(success_rate, 3),
                "avg_duration_ms": round(avg_ms, 1),
                "performance_score": round(perf_score, 3),
                "trend": trend,
            })

        return aggregated

    async def analyze_parameters(self, skill_name: str) -> list[dict]:
        """Analyze past successful runs to learn optimal parameter values."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SkillRun.input_data, SkillRun.status, SkillRun.duration_ms)
                .where(
                    SkillRun.skill_name == skill_name,
                    SkillRun.input_data.isnot(None),
                )
                .order_by(desc(SkillRun.started_at))
                .limit(200)
            )
            runs = result.all()

        if len(runs) < 5:
            return []

        # Build parameter distributions
        param_stats = defaultdict(lambda: {
            "values": Counter(),
            "success_values": Counter(),
            "fail_values": Counter(),
            "total": 0,
            "successes": 0,
        })

        for input_data, status, duration_ms in runs:
            if not isinstance(input_data, dict):
                continue
            for k, v in input_data.items():
                key = str(v) if not isinstance(v, str) else v
                param_stats[k]["values"][key] += 1
                param_stats[k]["total"] += 1
                if status == "success":
                    param_stats[k]["success_values"][key] += 1
                    param_stats[k]["successes"] += 1
                else:
                    param_stats[k]["fail_values"][key] += 1

        profiles = []
        for param_name, stats in param_stats.items():
            if stats["total"] < 3:
                continue

            # Find the value with the highest success rate
            best_value = None
            best_rate = 0
            for val, count in stats["values"].items():
                sc = stats["success_values"].get(val, 0)
                rate = sc / count if count > 0 else 0
                if rate > best_rate or (rate == best_rate and count > stats["values"].get(best_value, 0)):
                    best_rate = rate
                    best_value = val

            # Success correlation: how much does this param choice affect success
            overall_rate = stats["successes"] / stats["total"] if stats["total"] > 0 else 0
            correlation = best_rate - overall_rate

            # Upsert parameter profile
            async with AsyncSessionLocal() as session:
                existing = await session.execute(
                    select(SkillParameterProfile).where(
                        SkillParameterProfile.skill_name == skill_name,
                        SkillParameterProfile.parameter_name == param_name,
                    )
                )
                profile = existing.scalars().first()

                dist = {str(k): v for k, v in stats["values"].most_common(10)}
                if profile:
                    profile.optimal_value = best_value
                    profile.value_distribution = dist
                    profile.success_correlation = round(correlation, 3)
                    profile.sample_size = stats["total"]
                    profile.last_updated = utcnow()
                else:
                    profile = SkillParameterProfile(
                        skill_name=skill_name,
                        parameter_name=param_name,
                        optimal_value=best_value,
                        value_distribution=dist,
                        success_correlation=round(correlation, 3),
                        sample_size=stats["total"],
                    )
                    session.add(profile)

                await session.commit()

            if abs(correlation) > 0.1:
                await self._log_learning(
                    skill_name=skill_name,
                    event_type="parameter_tuned",
                    description=f"Parameter '{param_name}' optimal value: '{best_value}' (correlation: {correlation:.2f}, sample: {stats['total']})",
                    old_value={"distribution": dist},
                    new_value={"optimal": best_value, "correlation": correlation},
                    confidence=min(stats["total"] / 50, 1.0),
                    impact="medium" if abs(correlation) > 0.2 else "low",
                )

            profiles.append({
                "parameter": param_name,
                "optimal_value": best_value,
                "success_correlation": round(correlation, 3),
                "sample_size": stats["total"],
                "distribution": dist,
            })

        return profiles

    async def get_skill_score(self, skill_name: str) -> dict:
        """Get comprehensive ML score and insights for a skill."""
        latest = await SkillMetrics.get_latest(skill_name, "daily")
        history = await SkillMetrics.get_history(skill_name, "daily", limit=7)
        learning = await SkillLearningLog.get_recent(skill_name, limit=5)

        # Get parameter profiles
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SkillParameterProfile)
                .where(SkillParameterProfile.skill_name == skill_name)
                .order_by(desc(SkillParameterProfile.success_correlation))
            )
            param_profiles = list(result.scalars().all())

        if not latest:
            return {
                "skill_name": skill_name,
                "performance_score": None,
                "trend": "unknown",
                "message": "Insufficient data for ML analysis",
                "metrics": None,
                "history": [],
                "learning_events": [],
                "parameter_insights": [],
            }

        # Build score breakdown
        return {
            "skill_name": skill_name,
            "performance_score": round(latest.performance_score, 3),
            "trend": latest.trend,
            "success_rate": round(latest.success_rate, 3),
            "avg_duration_ms": round(latest.avg_duration_ms, 1),
            "total_runs": latest.total_runs,
            "avg_user_rating": round(latest.avg_user_rating, 2) if latest.avg_user_rating else None,
            "error_categories": latest.error_categories or {},
            "history": [
                {
                    "date": m.period_start.isoformat(),
                    "score": round(m.performance_score, 3),
                    "success_rate": round(m.success_rate, 3),
                    "total_runs": m.total_runs,
                    "avg_ms": round(m.avg_duration_ms, 1),
                }
                for m in reversed(history)
            ],
            "learning_events": [
                {
                    "type": le.event_type,
                    "description": le.description,
                    "confidence": round(le.confidence, 2),
                    "impact": le.impact,
                    "applied": le.applied,
                    "created_at": le.created_at.isoformat(),
                }
                for le in learning
            ],
            "parameter_insights": [
                {
                    "parameter": pp.parameter_name,
                    "optimal_value": pp.optimal_value,
                    "success_correlation": round(pp.success_correlation, 3),
                    "sample_size": pp.sample_size,
                    "distribution": pp.value_distribution or {},
                }
                for pp in param_profiles
            ],
        }

    async def get_all_scores(self) -> list[dict]:
        """Get ML scores for all skills."""
        all_metrics = await SkillMetrics.get_all_latest("daily")
        scores = []
        for m in all_metrics:
            scores.append({
                "skill_name": m.skill_name,
                "performance_score": round(m.performance_score, 3),
                "trend": m.trend,
                "success_rate": round(m.success_rate, 3),
                "total_runs": m.total_runs,
                "avg_duration_ms": round(m.avg_duration_ms, 1),
                "avg_user_rating": round(m.avg_user_rating, 2) if m.avg_user_rating else None,
            })
        scores.sort(key=lambda x: x["performance_score"], reverse=True)
        return scores

    async def submit_feedback(
        self,
        skill_name: str,
        rating: int,
        feedback_type: str = "thumbs",
        comment: str = None,
        skill_run_id: int = None,
        session_id: str = None,
        input_args: dict = None,
        output_snapshot: str = None,
    ) -> dict:
        """Record user feedback on a skill execution."""
        fb = await SkillFeedback.create(
            skill_name=skill_name,
            rating=rating,
            feedback_type=feedback_type,
            comment=comment,
            skill_run_id=skill_run_id,
            session_id=session_id,
            input_args=input_args,
            output_snapshot=output_snapshot[:2000] if output_snapshot else None,
        )

        # Log negative feedback as a learning signal
        if rating <= 0 or (feedback_type == "stars" and rating <= 2):
            await self._log_learning(
                skill_name=skill_name,
                event_type="negative_feedback",
                description=f"User rated output {rating}/{5 if feedback_type == 'stars' else 1}. Comment: {comment or 'none'}",
                confidence=0.7,
                impact="medium",
            )

        return {"id": fb.id, "skill_name": skill_name, "rating": rating}

    async def run_full_analysis(self) -> dict:
        """Run complete ML analysis cycle: aggregate, analyze parameters, detect patterns."""
        logger.info("[ML Engine] Starting full analysis cycle...")

        # 1. Aggregate metrics for all periods
        daily = await self.aggregate_metrics("daily")
        hourly = await self.aggregate_metrics("hourly")

        # 2. Analyze parameters for each active skill
        param_insights = {}
        skill_names = set(m["skill_name"] for m in daily)
        for sn in skill_names:
            insights = await self.analyze_parameters(sn)
            if insights:
                param_insights[sn] = insights

        # 3. Get all scores summary
        scores = await self.get_all_scores()

        summary = {
            "timestamp": utcnow().isoformat(),
            "skills_analyzed": len(skill_names),
            "daily_aggregations": len(daily),
            "hourly_aggregations": len(hourly),
            "parameter_insights": {k: len(v) for k, v in param_insights.items()},
            "top_performers": scores[:5] if scores else [],
            "needs_attention": [s for s in scores if s["performance_score"] < 0.5],
        }

        logger.info(f"[ML Engine] Analysis complete: {len(skill_names)} skills, {sum(m['total_runs'] for m in daily)} total runs")
        return summary

    # ── Private helpers ──────────────────────────────────────────────────

    def _calculate_performance_score(
        self,
        success_rate: float,
        avg_ms: float,
        avg_rating: Optional[float],
        trend: str,
        total_runs: int,
    ) -> float:
        """Composite 0-1 score combining multiple signals."""
        sr_score = success_rate

        # Latency score: <500ms = 1.0, >10s = 0.0
        latency_score = max(0, min(1, 1 - (avg_ms - 500) / 9500)) if avg_ms > 0 else 0.5

        # Rating score: normalize 1-5 to 0-1, or thumbs -1/1 to 0-1
        if avg_rating is not None:
            if avg_rating >= -1 and avg_rating <= 1:
                rating_score = (avg_rating + 1) / 2
            else:
                rating_score = (avg_rating - 1) / 4
        else:
            rating_score = 0.5  # neutral if no ratings

        # Trend bonus/penalty
        trend_score = {"improving": 0.7, "stable": 0.5, "degrading": 0.3}.get(trend, 0.5)

        # Reliability: more runs with consistent success = higher
        reliability = min(total_runs / 20, 1.0) * success_rate

        score = (
            self.WEIGHT_SUCCESS_RATE * sr_score
            + self.WEIGHT_LATENCY * latency_score
            + self.WEIGHT_USER_RATING * rating_score
            + self.WEIGHT_TREND * trend_score
            + self.WEIGHT_RELIABILITY * reliability
        )

        return max(0, min(1, score))

    async def _get_period_rating(self, skill_name: str, cutoff: datetime) -> tuple[Optional[float], int]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    func.avg(SkillFeedback.rating).label("avg"),
                    func.count(SkillFeedback.id).label("cnt"),
                )
                .where(
                    SkillFeedback.skill_name == skill_name,
                    SkillFeedback.created_at >= cutoff,
                )
            )
            row = result.first()
            if row and row[1] > 0:
                return float(row[0]), int(row[1])
            return None, 0

    async def _classify_errors(self, skill_name: str, cutoff: datetime) -> dict:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SkillRun.error_message)
                .where(
                    SkillRun.skill_name == skill_name,
                    SkillRun.status == "failed",
                    SkillRun.started_at >= cutoff,
                )
                .limit(50)
            )
            errors = [r[0] for r in result.all() if r[0]]

        categories = Counter()
        for err in errors:
            err_lower = err.lower()
            if "timeout" in err_lower:
                categories["timeout"] += 1
            elif "permission" in err_lower or "access" in err_lower:
                categories["permission"] += 1
            elif "import" in err_lower or "module" in err_lower:
                categories["import_error"] += 1
            elif "connection" in err_lower or "network" in err_lower:
                categories["network"] += 1
            elif "key" in err_lower or "not found" in err_lower:
                categories["key_error"] += 1
            else:
                categories["other"] += 1

        return dict(categories)

    async def _calculate_trend(
        self,
        skill_name: str,
        period: str,
        current_sr: float,
        current_ms: float,
    ) -> str:
        """Compare current metrics to previous period to detect trend."""
        history = await SkillMetrics.get_history(skill_name, period, limit=3)
        if len(history) < 2:
            return "stable"

        prev = history[1]  # Most recent previous
        sr_delta = current_sr - prev.success_rate
        ms_delta = current_ms - prev.avg_duration_ms

        sr_improving = sr_delta > 0.05
        sr_degrading = sr_delta < -0.05
        ms_improving = ms_delta < -100 and prev.avg_duration_ms > 0
        ms_degrading = ms_delta > 100 and prev.avg_duration_ms > 0

        if sr_improving or ms_improving:
            return "improving"
        elif sr_degrading or ms_degrading:
            return "degrading"
        return "stable"

    async def _detect_anomalies(
        self,
        skill_name: str,
        avg_ms: float,
        success_rate: float,
        period: str,
    ):
        """Flag anomalous performance patterns."""
        history = await SkillMetrics.get_history(skill_name, period, limit=7)
        if len(history) < 3:
            return

        hist_avg_ms = sum(m.avg_duration_ms for m in history) / len(history)
        hist_avg_sr = sum(m.success_rate for m in history) / len(history)

        # Latency anomaly
        if hist_avg_ms > 0 and avg_ms > hist_avg_ms * self.LATENCY_ANOMALY_FACTOR:
            await self._log_learning(
                skill_name=skill_name,
                event_type="anomaly_detected",
                description=f"Latency spike: {avg_ms:.0f}ms vs historical avg {hist_avg_ms:.0f}ms ({avg_ms/hist_avg_ms:.1f}x)",
                old_value={"avg_ms": hist_avg_ms},
                new_value={"avg_ms": avg_ms},
                confidence=0.8,
                impact="high",
            )

        # Error spike
        if success_rate < (1 - self.ERROR_SPIKE_THRESHOLD) and hist_avg_sr > 0.7:
            await self._log_learning(
                skill_name=skill_name,
                event_type="anomaly_detected",
                description=f"Error spike: success rate {success_rate:.1%} vs historical {hist_avg_sr:.1%}",
                old_value={"success_rate": hist_avg_sr},
                new_value={"success_rate": success_rate},
                confidence=0.85,
                impact="high",
            )

    async def _log_learning(
        self,
        skill_name: str,
        event_type: str,
        description: str,
        old_value: dict = None,
        new_value: dict = None,
        confidence: float = 0.5,
        impact: str = "low",
        applied: bool = False,
    ):
        try:
            await SkillLearningLog.create(
                skill_name=skill_name,
                event_type=event_type,
                description=description,
                old_value=old_value,
                new_value=new_value,
                confidence=confidence,
                impact=impact,
                applied=applied,
            )
        except Exception as e:
            logger.error(f"Failed to log learning event: {e}")


# Singleton
ml_engine = SkillMLEngine()
