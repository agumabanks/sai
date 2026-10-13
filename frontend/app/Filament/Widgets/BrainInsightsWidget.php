<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class BrainInsightsWidget extends Widget
{
    protected static string $view = 'filament.widgets.brain-insights-widget';

    protected static ?string $pollingInterval = '120s';

    protected static bool $isLazy = true;

    // ── Stat values ────────────────────────────────────────────────────────

    public int $totalMemories = 0;

    public int $learnedToday = 0;

    public float $llmCostToday = 0.0;

    public int $activeIssues = 0;

    public string $lastLearnedAt = '';

    public string $error = '';

    // ── Lifecycle ──────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadStats();
    }

    public function loadStats(): void
    {
        try {
            $engine = app(SanaaEngineService::class);

            // Total memories in store
            $allData = $engine->getAllMemories(null, null, 1, 0);
            $this->totalMemories = (int) ($allData['total'] ?? 0);

            // Auto-learned insights from today
            $insightsData = $engine->getBrainInsights();
            $items = $insightsData['items'] ?? [];
            $todayStart = now()->startOfDay()->toIso8601String();
            $this->learnedToday = collect($items)->filter(function ($item) use ($todayStart) {
                return isset($item['created_at']) && $item['created_at'] >= $todayStart;
            })->count();

            // LLM cost from today's resource usage
            $usageData = $engine->getResourceUsage();
            $usageItems = $usageData['usage'] ?? [];
            $todayUsage = collect($usageItems)->first(function ($item) use ($todayStart) {
                return isset($item['created_at']) && $item['created_at'] >= $todayStart;
            });
            $this->llmCostToday = round((float) ($todayUsage['metadata']['total_cost'] ?? 0), 4);

            // Active health issues (score < 70)
            $healthData = $engine->getBrainInsights('system_health');
            $healthItems = $healthData['items'] ?? [];
            $this->activeIssues = collect($healthItems)->filter(function ($item) {
                $score = $item['metadata']['health_score'] ?? null;

                return $score !== null && (float) $score < 70;
            })->count();

            // Last learned timestamp
            if (! empty($items)) {
                $latest = $items[0]['created_at'] ?? '';
                if ($latest) {
                    try {
                        $this->lastLearnedAt = \Carbon\Carbon::parse($latest)->diffForHumans();
                    } catch (\Exception) {
                        $this->lastLearnedAt = $latest;
                    }
                }
            }

        } catch (\Exception $e) {
            $this->error = 'Brain stats unavailable: '.$e->getMessage();
        }
    }

    public function refresh(): void
    {
        $this->loadStats();
    }
}
