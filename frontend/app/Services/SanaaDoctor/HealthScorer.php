<?php

namespace App\Services\SanaaDoctor;

class HealthScorer
{
    /**
     * Calculate health score, status, and flags from signals and thresholds.
     *
     * @param  array<string, mixed>  $signals
     * @param  array<string, mixed>  $thresholds
     * @return array{score: int, status: string, flags: array<int, string>}
     */
    public function score(array $signals, array $thresholds): array
    {
        $score = 100;
        $flags = [];

        $queueDepthMax = $thresholds['queue_depth_max'] ?? 50;
        if (($signals['queue_depth'] ?? 0) > $queueDepthMax) {
            $score -= 10;
            $flags[] = 'high queue depth';
        }

        $failedJobsMax = $thresholds['failed_jobs_1h_max'] ?? 5;
        if (($signals['failed_jobs_1h'] ?? 0) > $failedJobsMax) {
            $score -= 20;
            $flags[] = 'high failed jobs';
        }

        $dbLatencyMax = $thresholds['db_latency_ms_max'] ?? 300;
        if (($signals['db_latency_ms'] ?? 0) > $dbLatencyMax) {
            $score -= 15;
            $flags[] = 'high db latency';
        }

        if (($signals['redis_ok'] ?? true) === false) {
            $score -= 25;
            $flags[] = 'redis down';
        }

        $errorRateMax = $thresholds['error_rate_1h_max'] ?? 5.0;
        if (isset($signals['error_rate_1h']) && $signals['error_rate_1h'] !== null && $signals['error_rate_1h'] > $errorRateMax) {
            $score -= 20;
            $flags[] = 'high error rate';
        }

        $lastOrderStaleMinutes = $thresholds['last_order_stale_minutes'] ?? null;
        if ($lastOrderStaleMinutes !== null && isset($signals['last_order_at']) && $signals['last_order_at'] !== null) {
            $lastOrderAt = \Carbon\Carbon::parse($signals['last_order_at']);
            if ($lastOrderAt->diffInMinutes(now()) > $lastOrderStaleMinutes) {
                $score -= 15;
                $flags[] = 'stale orders';
            }
        }

        $diskFreePercent = $signals['disk_free_percent'] ?? 100;
        if ($diskFreePercent < 5) {
            $score -= 40;
            $flags[] = 'critical disk space';
        } elseif ($diskFreePercent < 15) {
            $score -= 20;
            $flags[] = 'low disk space';
        }

        $score = max(0, min(100, $score));

        if ($score >= 80) {
            $status = 'healthy';
        } elseif ($score >= 50) {
            $status = 'degraded';
        } else {
            $status = 'critical';
        }

        return [
            'score' => $score,
            'status' => $status,
            'flags' => $flags,
        ];
    }
}
