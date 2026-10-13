<?php

namespace App\Support;

use App\Models\SanaaHealthLog;
use App\Services\SanaaDoctor\HealDispatcher;
use App\Services\SanaaDoctor\HealthScorer;
use Illuminate\Support\Facades\Artisan;

class SanaaEcosystem
{
    public static function healApp(string $appKey): array
    {
        $configured = config('sanaa_apps.apps', []);
        $appConfig = $configured[$appKey] ?? null;

        if (! $appConfig) {
            return ['success' => false, 'error' => 'Unknown app key'];
        }

        if (empty($appConfig['heal_url'])) {
            return [
                'success' => false,
                'error' => 'This app has no heal endpoint configured',
                'app' => $appKey,
            ];
        }

        $log = SanaaHealthLog::query()
            ->where('app', $appKey)
            ->orderByDesc('created_at')
            ->first();

        $signals = is_array($log?->signals) ? $log->signals : [];
        if ($log && $signals === [] && ($log->status ?? '') === 'critical') {
            return [
                'success' => false,
                'error' => 'App is unreachable. Heal cannot run until the health endpoint responds.',
                'app' => $appKey,
            ];
        }

        $scorer = app(HealthScorer::class);
        $scored = $scorer->score($signals, $appConfig['thresholds'] ?? []);
        $flags = $scored['flags'] ?: ['manual_heal'];

        $dispatcher = app(HealDispatcher::class);
        $result = $dispatcher->dispatch(
            $appConfig,
            $flags,
            $log?->groq_diagnosis ?? 'Manual heal requested from Sanaa OS',
            $log?->recommended_action ?? 'Run automated recovery actions',
        );

        try {
            Artisan::call('sanaa:doctor:poll');
        } catch (\Throwable) {
            // Non-fatal: heal may have succeeded even if poll fails.
        }

        $healResponse = $result['heal_response'];
        $healed = (bool) ($healResponse['healed'] ?? false);
        $actionsTaken = $healResponse['actions_taken'] ?? [];
        $actionTaken = $result['action_taken'];

        if ($actionTaken === 'heal_triggered' && ! $healed && $actionsTaken === []) {
            return [
                'success' => true,
                'healed' => false,
                'app' => $appKey,
                'action_taken' => $actionTaken,
                'flags' => $flags,
                'heal_response' => $healResponse,
                'message' => 'Heal webhook accepted but no recovery actions ran for the current issue flags.',
            ];
        }

        if ($actionTaken === 'alert_sent') {
            return [
                'success' => false,
                'healed' => false,
                'app' => $appKey,
                'action_taken' => $actionTaken,
                'flags' => $flags,
                'heal_response' => $healResponse,
                'error' => $healResponse['error'] ?? 'Heal webhook failed or is not configured',
            ];
        }

        return [
            'success' => true,
            'healed' => $healed,
            'app' => $appKey,
            'action_taken' => $actionTaken,
            'flags' => $flags,
            'heal_response' => $healResponse,
            'message' => $healed
                ? 'Recovery actions completed: '.implode(', ', $actionsTaken)
                : ($actionsTaken ? 'Heal ran: '.implode(', ', $actionsTaken) : 'Heal dispatched'),
        ];
    }

    public static function pollAll(): array
    {
        Artisan::call('sanaa:doctor:poll');

        return [
            'success' => true,
            'output' => trim(Artisan::output()),
        ];
    }

    public static function overview(): array
    {
        $configured = config('sanaa_apps.apps', []);

        $subquery = SanaaHealthLog::query()
            ->select('app', \Illuminate\Support\Facades\DB::raw('MAX(created_at) as max_created_at'))
            ->groupBy('app');

        $logs = SanaaHealthLog::query()
            ->from('sanaa_health_log as main')
            ->joinSub($subquery, 'latest', function ($join): void {
                $join->on('main.app', '=', 'latest.app')
                    ->on('main.created_at', '=', 'latest.max_created_at');
            })
            ->select('main.*')
            ->get()
            ->keyBy('app');

        $apps = collect($configured)->map(function (array $app, string $key) use ($logs): array {
            $log = $logs->get($key);
            $healthUrl = $app['health_url'] ?? null;
            $healUrl = $app['heal_url'] ?? null;

            return [
                'key' => $key,
                'name' => $app['name'] ?? $key,
                'type' => $app['type'] ?? 'platform',
                'tenant' => $app['tenant'] ?? null,
                'status' => $log?->status ?? 'unknown',
                'score' => $log?->score,
                'checked_at' => $log?->created_at?->toIso8601String(),
                'health_url' => $healthUrl,
                'heal_url' => $healUrl,
                'can_heal' => ! empty($healUrl),
                'external_url' => $healthUrl ? preg_replace('#/api/health$#', '', $healthUrl) : null,
                'has_log' => $log !== null,
                'log_id' => $log?->id,
                'signals' => $log?->signals ?? [],
                'groq_diagnosis' => $log?->groq_diagnosis,
                'recommended_action' => $log?->recommended_action,
                'action_taken' => $log?->action_taken,
            ];
        })->values()->all();

        return [
            'success' => true,
            'generated_at' => now()->toIso8601String(),
            'summary' => SanaaShell::ecosystemSummary($apps),
            'apps' => $apps,
            'doctor_url' => route('filament.admin.pages.sanaa-doctor'),
        ];
    }
}
